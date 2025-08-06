import os
import aiohttp
import asyncio
import time
import logging
import threading
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Union
import datetime
import json
import uuid
from pathlib import Path
from tqdm import tqdm
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import uvicorn
import random
import hashlib
import weakref
from collections import defaultdict
import signal
import sys

# Load .env file
load_dotenv()

# Configure logging with better formatting
log_level = os.getenv("LOG_LEVEL", "info").upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('translation_service.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Get environment variables configuration
MAX_REQUESTS_PER_MINUTE = int(os.getenv("MAX_REQUESTS_PER_MINUTE", 60))
TIMEOUT = int(os.getenv("TIMEOUT", 30))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", 5))
CHECK_TIMEOUT = int(os.getenv("CHECK_TIMEOUT", 5))

class RateLimiter:
    def __init__(self, max_requests: int, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
        self.lock = asyncio.Lock()
        self.client_requests = defaultdict(list)  # Per-client rate limiting
    
    async def acquire(self, client_ip: str = None):
        async with self.lock:
            now = time.time()
            
            # Global rate limiting
            self.requests = [req_time for req_time in self.requests if now - req_time < self.time_window]
            if len(self.requests) >= self.max_requests:
                raise HTTPException(status_code=429, detail="Global rate limit exceeded")
            
            # Per-client rate limiting (stricter)
            if client_ip:
                client_limit = min(self.max_requests // 4, 30)  # Quarter of global limit per client
                self.client_requests[client_ip] = [
                    req_time for req_time in self.client_requests[client_ip] 
                    if now - req_time < self.time_window
                ]
                if len(self.client_requests[client_ip]) >= client_limit:
                    raise HTTPException(status_code=429, detail="Client rate limit exceeded")
                self.client_requests[client_ip].append(now)
            
            self.requests.append(now)
            return True

class URLStatus:
    def __init__(self):
        self.status_dict: Dict[str, dict] = {}
        self.lock = asyncio.Lock()
        self.max_workers = MAX_WORKERS
        self.check_timeout = CHECK_TIMEOUT
        self.session_pool = None
        
    async def get_session_pool(self):
        """Get or create session pool for connection reuse"""
        if self.session_pool is None:
            connector = aiohttp.TCPConnector(
                limit=100,
                limit_per_host=20,
                ttl_dns_cache=300,
                use_dns_cache=True,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            timeout = aiohttp.ClientTimeout(total=self.check_timeout)
            self.session_pool = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    'User-Agent': 'DeepLX-API-Checker/1.0',
                    'Accept': 'application/json',
                    'Connection': 'keep-alive'
                }
            )
        return self.session_pool
    
    async def check_url(self, url: str) -> Dict:
        """Check the availability of a single URL with enhanced validation."""
        test_data = {
            "text": os.getenv("TEST_TEXT", "Hello, world"),
            "source_lang": os.getenv("TEST_SOURCE_LANG", "EN"),
            "target_lang": os.getenv("TEST_TARGET_LANG", "ZH"),
            "request_id": str(uuid.uuid4())
        }
        
        session = await self.get_session_pool()
        
        try:
            start_time = time.time()
            # Add cache busting parameter
            cache_buster = f"nocache={int(time.time() * 1000)}"
            request_url = f"{url}{'&' if '?' in url else '?'}{cache_buster}"
            
            async with session.post(request_url, json=test_data) as response:
                latency = time.time() - start_time
                
                if response.status == 200:
                    try:
                        result = await response.json()
                        if 'data' in result and result.get("data"):
                            response_text = str(result.get("data"))
                            # Enhanced validation
                            if (len(response_text) > 0 and 
                                response_text.strip() and 
                                response_text != test_data["text"]):  # Ensure translation occurred
                                
                                await self.update_status(url, True, latency, len(response_text))
                                return {
                                    "url": url,
                                    "available": True,
                                    "latency": round(latency, 3),
                                    "error": None,
                                    "response_length": len(response_text),
                                    "timestamp": time.time()
                                }
                            else:
                                error_text = "Empty or invalid translation response"
                        else:
                            error_text = "Invalid response format - missing 'data' field"
                    except json.JSONDecodeError:
                        error_text = "Invalid JSON response"
                else:
                    error_text = f"HTTP {response.status}"
                    try:
                        error_detail = await response.text()
                        if len(error_detail) < 200:  # Avoid logging huge error messages
                            error_text += f": {error_detail}"
                    except:
                        pass
                        
                await self.update_status(url, False)
                return {
                    "url": url,
                    "available": False,
                    "latency": None,
                    "error": error_text,
                    "timestamp": time.time()
                }
                
        except asyncio.TimeoutError:
            await self.update_status(url, False)
            return {
                "url": url,
                "available": False,
                "latency": None,
                "error": "Connection timeout",
                "timestamp": time.time()
            }
        except Exception as e:
            await self.update_status(url, False)
            return {
                "url": url,
                "available": False,
                "latency": None,
                "error": f"Connection error: {str(e)[:100]}",
                "timestamp": time.time()
            }
    
    async def check_urls_concurrent(self, urls: List[str]) -> List[Dict]:
        """Check multiple URLs concurrently with improved progress tracking."""
        if not urls:
            return []
            
        results = []
        # Create semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(min(self.max_workers, len(urls)))
        
        async def check_with_semaphore(url):
            async with semaphore:
                return await self.check_url(url)
        
        # Create tasks
        tasks = [asyncio.create_task(check_with_semaphore(url)) for url in urls]
        
        # Process with progress tracking
        completed = 0
        try:
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)
                completed += 1
                if completed % 10 == 0 or completed == len(urls):
                    logger.info(f"URL check progress: {completed}/{len(urls)} completed")
        except Exception as e:
            logger.error(f"Error in concurrent URL checking: {e}")
            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
        
        # Sort by latency (available URLs first, then by latency)
        available_results = [r for r in results if r["available"]]
        unavailable_results = [r for r in results if not r["available"]]
        
        available_results.sort(key=lambda x: x["latency"] or float('inf'))
        
        return available_results + unavailable_results
    
    async def update_status(self, url: str, status: bool, latency: float = None, response_length: int = None):
        async with self.lock:
            current_time = time.time()
            self.status_dict[url] = {
                "available": status,
                "latency": latency,
                "response_length": response_length,
                "last_check": current_time,
                "last_success": current_time if status else self.status_dict.get(url, {}).get("last_success"),
                "consecutive_failures": 0 if status else self.status_dict.get(url, {}).get("consecutive_failures", 0) + 1,
                "total_checks": self.status_dict.get(url, {}).get("total_checks", 0) + 1,
                "success_rate": None  # Will be calculated when needed
            }
            
            # Calculate success rate
            if self.status_dict[url]["total_checks"] > 0:
                failures = self.status_dict[url]["consecutive_failures"]
                total = self.status_dict[url]["total_checks"]
                self.status_dict[url]["success_rate"] = max(0, (total - failures) / total)
    
    def get_status(self, url: str) -> dict:
        return self.status_dict.get(url, {})
    
    def get_all_status(self) -> dict:
        return self.status_dict.copy()
    
    async def cleanup(self):
        """Cleanup session pool"""
        if self.session_pool:
            await self.session_pool.close()

class URLRotator:
    def __init__(self, urls):
        self.urls = [url.strip() for url in urls if url.strip()]
        if not self.urls:
            raise ValueError("No valid URLs provided")
        self.current_index = 0
        self.lock = asyncio.Lock()
        self.url_status = URLStatus()
        # Enhanced tracking
        self.request_counts = {url: 0 for url in self.urls}
        self.last_used = {url: 0 for url in self.urls}
        self.url_weights = {url: 1.0 for url in self.urls}  # Dynamic weighting
    
    async def get_next_url(self):
        async with self.lock:
            now = time.time()
            
            # Get available URLs with enhanced scoring
            scored_urls = []
            
            for url in self.urls:
                status = self.url_status.get_status(url)
                
                # Skip URLs with too many consecutive failures
                if status.get('consecutive_failures', 0) > 5:
                    continue
                
                if status.get('available', True):  # Default to available
                    # Enhanced scoring algorithm
                    base_latency = status.get('latency', 1.0)
                    request_load = self.request_counts.get(url, 0) * 0.005  # Load factor
                    recent_usage = max(0, 10 - (now - self.last_used.get(url, 0))) * 0.05  # Recent usage penalty
                    success_rate = status.get('success_rate', 1.0)
                    weight = self.url_weights.get(url, 1.0)
                    
                    # Final score (lower is better)
                    score = (base_latency + request_load + recent_usage) / (success_rate * weight)
                    scored_urls.append((url, score))
            
            if not scored_urls:
                # Fallback: try any URL if all seem unavailable
                if self.urls:
                    selected_url = random.choice(self.urls)
                    logger.warning(f"No available URLs found, using fallback: {selected_url}")
                else:
                    raise HTTPException(status_code=503, detail="No available translation endpoints")
            else:
                # Select best URL (lowest score)
                scored_urls.sort(key=lambda x: x[1])
                selected_url = scored_urls[0][0]
            
            # Update tracking
            self.request_counts[selected_url] = self.request_counts.get(selected_url, 0) + 1
            self.last_used[selected_url] = now
            
            return selected_url
    
    def update_urls(self, new_urls):
        new_urls = [url.strip() for url in new_urls if url.strip()]
        if not new_urls:
            logger.warning("No valid URLs provided for update")
            return
            
        # Preserve existing statistics for URLs that remain
        old_request_counts = self.request_counts.copy()
        old_last_used = self.last_used.copy()
        old_weights = self.url_weights.copy()
        
        self.urls = new_urls
        self.request_counts = {url: old_request_counts.get(url, 0) for url in new_urls}
        self.last_used = {url: old_last_used.get(url, 0) for url in new_urls}
        self.url_weights = {url: old_weights.get(url, 1.0) for url in new_urls}
        
        logger.info(f"URLs updated: {len(new_urls)} URLs now active")
    
    async def cleanup(self):
        """Cleanup resources"""
        await self.url_status.cleanup()

class ChatRequest(BaseModel):
    messages: List[dict]
    stream: bool = False
    model: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None

class URLCheckResult(BaseModel):
    url: str
    available: bool
    latency: Optional[float]
    error: Optional[str]
    response_length: Optional[int] = None
    timestamp: Optional[float] = None

class LogRequestsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.request_cache = {}  # Simple request deduplication cache
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        client_ip = request.client.host if request.client else "unknown"
        request_id = str(uuid.uuid4())[:8]
        
        try:
            # Log request start
            logger.debug(f"[{request_id}] Request from {client_ip}: {request.method} {request.url.path}")
            
            # Add request context
            request.state.request_id = request_id
            request.state.client_ip = client_ip
            request.state.start_time = start_time
            
            response = await call_next(request)
            
            duration = time.time() - start_time
            logger.info(f"[{request_id}] Completed in {duration:.3f}s - Status: {response.status_code}")
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[{request_id}] Error after {duration:.3f}s: {str(e)}")
            raise

# Define FastAPI application with enhanced lifespan handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Translation Service API...")
    
    # Start background tasks
    check_task = asyncio.create_task(periodic_url_check())
    
    # Setup graceful shutdown handling
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        check_task.cancel()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        yield  # Application runs here
    finally:
        # Shutdown
        logger.info("Shutting down Translation Service API...")
        check_task.cancel()
        try:
            await check_task
        except asyncio.CancelledError:
            pass
        
        # Cleanup resources
        await url_rotator.cleanup()
        logger.info("Shutdown complete.")

app = FastAPI(
    title="Translation Service API",
    description="High-performance DeepLX translation service with load balancing",
    version="1.1.0",
    lifespan=lifespan
)

app.add_middleware(LogRequestsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enhanced initialization
TRANSLATION_API_URLS = os.getenv('TRANSLATION_API_URLS', '').split(',')
TRANSLATION_API_URLS = [url for url in TRANSLATION_API_URLS if url]
if not TRANSLATION_API_URLS:
    raise ValueError("No valid URLs provided in the environment variable TRANSLATION_API_URLS.")

url_rotator = URLRotator(TRANSLATION_API_URLS)
rate_limiter = RateLimiter(MAX_REQUESTS_PER_MINUTE)

def get_streaming_support(request: Request) -> bool:
    """Determine if streaming response is supported."""
    global_streaming = os.getenv("ENABLE_STREAMING", "true").lower() == "true"
    client_supports_sse = "text/event-stream" in request.headers.get("Accept", "")
    return global_streaming and client_supports_sse

def safe_write_text(text: str, filepath: str):
    """Safely write text to file, handling encoding issues."""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Clean text by removing or replacing problematic characters
        cleaned_text = text.encode('utf-8', errors='replace').decode('utf-8')
        
        # Write with explicit UTF-8 encoding
        with open(filepath, "w", encoding="utf-8", errors='replace') as f:
            f.write(cleaned_text)
        return True
    except Exception as e:
        logger.error(f"Error writing to file {filepath}: {e}")
        return False

async def translate_single(text: str, source_lang: str, target_lang: str, session: aiohttp.ClientSession):
    """Perform a single translation with enhanced error handling."""
    if source_lang == target_lang:
        return {target_lang: text}
    
    max_retries = min(len(TRANSLATION_API_URLS), 5)  # Cap retries at 5
    if max_retries == 0:
        max_retries = 3
    
    last_error = None
    tried_urls = set()
    
    for attempt in range(max_retries):
        url = await url_rotator.get_next_url()
        
        # Avoid immediate retry on same URL
        retry_count = 0
        while url in tried_urls and retry_count < 3:
            await asyncio.sleep(0.1)  # Brief pause
            url = await url_rotator.get_next_url()
            retry_count += 1
        
        tried_urls.add(url)
        
        request_id = str(uuid.uuid4())
        
        payload = {
            "text": text,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "request_id": request_id
        } if source_lang else {
            "text": text,
            "target_lang": target_lang,
            "request_id": request_id
        }
        
        start_time = time.time()
        try:
            # Enhanced request with cache busting
            cache_buster = f"nocache={int(time.time() * 1000)}&retry={attempt}"
            request_url = f"{url}{'&' if '?' in url else '?'}{cache_buster}"
            
            async with session.post(
                request_url, 
                json=payload, 
                timeout=aiohttp.ClientTimeout(total=TIMEOUT),
                headers={
                    "Cache-Control": "no-cache",
                    "X-Request-ID": request_id
                }
            ) as response:
                duration = time.time() - start_time
                
                if response.status != 200:
                    error_text = await response.text()
                    last_error = f"HTTP {response.status}: {error_text[:200]}"
                    await url_rotator.url_status.update_status(url, False)
                    logger.warning(f"Translation attempt {attempt + 1} failed on {url}: {last_error}")
                    continue
                
                try:
                    result = await response.json()
                    if 'data' in result and result.get("data"):
                        translated_text = result.get('data', '')
                        if translated_text and translated_text.strip():
                            await url_rotator.url_status.update_status(url, True, duration, len(translated_text))
                            logger.debug(f"Translation successful on {url} in {duration:.3f}s")
                            return {target_lang: translated_text}
                    
                    last_error = f"Invalid API response: {json.dumps(result)[:200]}"
                except json.JSONDecodeError as e:
                    last_error = f"JSON decode error: {str(e)}"
                
                await url_rotator.url_status.update_status(url, False)
                continue
                
        except asyncio.TimeoutError:
            last_error = f"Request timeout ({TIMEOUT}s)"
            await url_rotator.url_status.update_status(url, False)
        except Exception as e:
            last_error = f"Request error: {str(e)[:200]}"
            await url_rotator.url_status.update_status(url, False)
        
        # Exponential backoff for retries
        if attempt < max_retries - 1:
            backoff_time = min(2 ** attempt * 0.1, 2.0)
            await asyncio.sleep(backoff_time)
    
    raise HTTPException(
        status_code=503,
        detail=f"Translation failed after {max_retries} attempts. Last error: {last_error}"
    )

@app.post("/v1/chat/completions")
async def chat_completions(chat_request: ChatRequest, request: Request):
    """Main endpoint to handle translation requests with enhanced features."""
    try:
        client_ip = getattr(request.state, 'client_ip', 'unknown')
        request_id = getattr(request.state, 'request_id', str(uuid.uuid4())[:8])
        
        await rate_limiter.acquire(client_ip)
        
        logger.debug(f"[{request_id}] Processing chat completion request")
        
        # Enhanced model parsing
        model_parts = chat_request.model.split('-')
        if len(model_parts) >= 3:
            source_lang = model_parts[1].upper()
            target_lang = model_parts[2].upper()
        elif len(model_parts) >= 2:
            source_lang = ""
            target_lang = model_parts[1].upper()
        else:
            logger.error(f"[{request_id}] Invalid model format: {chat_request.model}")
            raise HTTPException(status_code=400, detail="Invalid model format. Use format: 'model-SOURCE-TARGET' or 'model-TARGET'")
        
        # Extract and validate user message
        text = ""
        for message in chat_request.messages:
            if message.get('role') == 'user':
                content = message.get('content', "")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, dict):
                    text = content.get('text', '')
                break
        
        if not text or not text.strip():
            logger.warning(f"[{request_id}] Empty user message")
            raise HTTPException(status_code=400, detail="No valid user message found")
        
        # Text length validation
        max_length = int(os.getenv("MAX_TEXT_LENGTH", 5000))
        if len(text) > max_length:
            raise HTTPException(status_code=400, detail=f"Text too long (max {max_length} characters)")
        
        logger.info(f"[{request_id}] Translating {len(text)} chars: {source_lang or 'AUTO'} -> {target_lang}")
        
        # Determine response type
        supports_streaming = get_streaming_support(request)
        use_streaming = chat_request.stream and supports_streaming
        
        if use_streaming:
            async def sse_translate():
                try:
                    chat_message_id = str(uuid.uuid4())
                    timestamp = int(datetime.datetime.now().timestamp())
                    
                    # Create fresh session for this request
                    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
                    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
                    
                    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                        translation_result = await translate_single(text, source_lang, target_lang, session)
                        translated_text = translation_result.get(target_lang, "")
                        
                        logger.info(f"[{request_id}] Streaming translation completed, {len(translated_text)} chars")
                        
                        # Send translation in chunks for better UX
                        chunk_size = 100
                        for i in range(0, len(translated_text), chunk_size):
                            chunk = translated_text[i:i + chunk_size]
                            data = {
                                "id": chat_message_id,
                                "object": "chat.completion.chunk",
                                "created": timestamp,
                                "model": chat_request.model,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": chunk},
                                    "finish_reason": None
                                }]
                            }
                            yield f"data: {json.dumps(data)}\n\n"
                            await asyncio.sleep(0.01)  # Small delay for chunking effect
                        
                        # Send finish signal
                        finish_data = {
                            "id": chat_message_id,
                            "object": "chat.completion.chunk",
                            "created": timestamp,
                            "model": chat_request.model,
                            "choices": [{
                                "index": 0,
                                "delta": {},
                                "finish_reason": "stop"
                            }]
                        }
                        yield f"data: {json.dumps(finish_data)}\n\n"
                        
                except HTTPException as e:
                    logger.error(f"[{request_id}] Streaming HTTPException: {e.detail}")
                    error_data = {
                        "error": {
                            "message": e.detail,
                            "type": "translation_error",
                            "code": e.status_code
                        }
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                except Exception as e:
                    logger.exception(f"[{request_id}] Streaming unexpected error: {str(e)}")
                    error_data = {
                        "error": {
                            "message": "Internal server error during translation",
                            "type": "internal_error",
                            "code": 500
                        }
                    }
                    yield f"data: {json.dumps(error_data)}\n\n"
                finally:
                    yield "data: [DONE]\n\n"
            
            return StreamingResponse(
                sse_translate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Request-ID": request_id
                }
            )
        else:
            # Non-streaming response
            connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
            timeout = aiohttp.ClientTimeout(total=TIMEOUT)
            
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                translation_result = await translate_single(text, source_lang, target_lang, session)
                translated_text = translation_result.get(target_lang, "")
                
                logger.info(f"[{request_id}] Translation completed, {len(translated_text)} chars")
                
                response_data = {
                    "id": str(uuid.uuid4()),
                    "object": "chat.completion",
                    "created": int(datetime.datetime.now().timestamp()),
                    "model": chat_request.model,
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": translated_text
                        },
                        "finish_reason": "stop"
                    }],
                    "usage": {
                        "prompt_tokens": len(text.split()),
                        "completion_tokens": len(translated_text.split()),
                        "total_tokens": len(text.split()) + len(translated_text.split())
                    }
                }
                
                return JSONResponse(
                    content=response_data,
                    headers={"X-Request-ID": request_id}
                )
                
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[{getattr(request.state, 'request_id', 'unknown')}] Unexpected server error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/v1/check-and-export-urls")
async def check_and_export_urls():
    """Check and export available URLs with enhanced reporting."""
    try:
        urls = os.getenv('TRANSLATION_API_URLS', '').split(',')
        urls = [url.strip() for url in urls if url.strip()]
        
        if not urls:
            return JSONResponse(
                content={"error": "No URLs found in environment variables"},
                status_code=400
            )
        
        logger.info(f"Starting URL check for {len(urls)} URLs")
        
        # Concurrently check URLs with enhanced validation
        results = await url_rotator.url_status.check_urls_concurrent(urls)
        
        # Separate available and unavailable URLs
        available_endpoints = [result for result in results if result['available']]
        unavailable_endpoints = [result for result in results if not result['available']]
        
        # Sort available endpoints by latency
        available_endpoints.sort(key=lambda x: x.get('latency', float('inf')))
        
        # Generate enhanced output
        output_format = os.getenv("RESULT_FORMAT", "detailed")
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if output_format == "detailed":
            output_text = f"DeepLX URL Check Report - {timestamp}\n"
            output_text += "=" * 80 + "\n\n"
            
            output_text += f"📊 Summary:\n"
            output_text += f"   Total URLs checked: {len(urls)}\n"
            output_text += f"   Available URLs: {len(available_endpoints)}\n"
            output_text += f"   Unavailable URLs: {len(unavailable_endpoints)}\n"
            output_text += f"   Success rate: {len(available_endpoints)/len(urls)*100:.1f}%\n\n"
            
            if available_endpoints:
                output_text += "✅ Available DeepLX Endpoints (sorted by latency):\n"
                output_text += "-" * 60 + "\n"
                for i, endpoint in enumerate(available_endpoints, 1):
                    latency = endpoint.get('latency', 0)
                    length = endpoint.get('response_length', 0)
                    output_text += f"{i:2d}. 🚀 ({latency:.3f}s, {length}B) {endpoint['url']}\n"
                output_text += "-" * 60 + "\n\n"
            
            if unavailable_endpoints:
                output_text += "❌ Unavailable Endpoints:\n"
                output_text += "-" * 60 + "\n"
                for i, endpoint in enumerate(unavailable_endpoints, 1):
                    error = endpoint.get('error', 'Unknown error')[:50]
                    output_text += f"{i:2d}. ⚠️  {endpoint['url']}\n"
                    output_text += f"      Error: {error}\n"
                output_text += "-" * 60 + "\n\n"
            
            # Performance statistics
            if available_endpoints:
                latencies = [e['latency'] for e in available_endpoints if e.get('latency')]
                if latencies:
                    avg_latency = sum(latencies) / len(latencies)
                    min_latency = min(latencies)
                    max_latency = max(latencies)
                    output_text += f"📈 Performance Statistics:\n"
                    output_text += f"   Average latency: {avg_latency:.3f}s\n"
                    output_text += f"   Best latency: {min_latency:.3f}s\n"
                    output_text += f"   Worst latency: {max_latency:.3f}s\n\n"
        else:
            # Compact format
            endpoints_str = ", ".join([r["url"] for r in available_endpoints])
            output_text = f"\n{timestamp}\n"
            output_text += f"DeepLX👌：({len(available_endpoints)}/{len(urls)}) {endpoints_str}\n"
        
        # Save to file with safe encoding
        export_path = os.getenv("EXPORT_PATH", "./results/useful.txt")
        success = safe_write_text(output_text, export_path)
        
        if not success:
            logger.warning("Failed to write results to file, but check completed successfully")
        
        # Auto-update URLs if configured
        updated_urls = False
        if os.getenv("AUTO_UPDATE_URLS", "true").lower() == "true":
            min_required = int(os.getenv("MIN_AVAILABLE_URLS", 2))
            if len(available_endpoints) >= min_required:
                new_urls = [endpoint["url"] for endpoint in available_endpoints]
                url_rotator.update_urls(new_urls)
                # Update environment variable for this session
                os.environ['TRANSLATION_API_URLS'] = ",".join(new_urls)
                updated_urls = True
                logger.info(f"URLs auto-updated: {len(new_urls)} active URLs")
            else:
                logger.warning(f"Not enough available URLs ({len(available_endpoints)}) for auto-update (min: {min_required})")
        
        response_data = {
            "status": "success",
            "message": "URLs checked and exported successfully",
            "timestamp": timestamp,
            "summary": {
                "total_checked": len(urls),
                "available": len(available_endpoints),
                "unavailable": len(unavailable_endpoints),
                "success_rate": round(len(available_endpoints)/len(urls)*100, 1) if urls else 0
            },
            "available_urls": available_endpoints,
            "unavailable_urls": unavailable_endpoints[:10],  # Limit to first 10 failures
            "export_path": export_path,
            "file_written": success,
            "urls_updated": updated_urls
        }
        
        # Add performance stats
        if available_endpoints:
            latencies = [e.get('latency') for e in available_endpoints if e.get('latency')]
            if latencies:
                response_data["performance"] = {
                    "avg_latency": round(sum(latencies) / len(latencies), 3),
                    "min_latency": round(min(latencies), 3),
                    "max_latency": round(max(latencies), 3)
                }
        
        return JSONResponse(content=response_data, status_code=200)
        
    except Exception as e:
        logger.exception("Error in check_and_export_urls")
        return JSONResponse(
            content={
                "error": f"Failed to check URLs: {str(e)}",
                "timestamp": datetime.datetime.now().isoformat()
            },
            status_code=500
        )

@app.get("/v1/urls/status")
async def get_urls_status():
    """Get the current status of all URLs with enhanced information."""
    try:
        all_status = url_rotator.url_status.get_all_status()
        current_time = time.time()
        
        # Enhance status information
        enhanced_status = {}
        available_count = 0
        
        for url, status in all_status.items():
            enhanced_status[url] = status.copy()
            
            # Add computed fields
            if status.get('last_check'):
                enhanced_status[url]['seconds_since_check'] = int(current_time - status['last_check'])
            
            if status.get('last_success'):
                enhanced_status[url]['seconds_since_success'] = int(current_time - status['last_success'])
                if current_time - status['last_success'] < 300:  # 5 minutes
                    available_count += 1
            
            # Add health score (0-100)
            health_score = 100
            if status.get('consecutive_failures', 0) > 0:
                health_score -= min(status['consecutive_failures'] * 20, 80)
            if status.get('latency', 0) > 2.0:
                health_score -= 10
            enhanced_status[url]['health_score'] = max(0, health_score)
        
        return JSONResponse(content={
            "status": "healthy" if available_count > 0 else "degraded",
            "timestamp": datetime.datetime.now().isoformat(),
            "summary": {
                "total_urls": len(url_rotator.urls),
                "available_urls": available_count,
                "degraded_urls": len(all_status) - available_count,
                "avg_latency": None
            },
            "urls_status": enhanced_status,
            "request_stats": {
                "total_requests": sum(url_rotator.request_counts.values()),
                "request_distribution": url_rotator.request_counts
            }
        })
    except Exception as e:
        logger.exception("Error in get_urls_status")
        return JSONResponse(
            content={"error": f"Failed to get URL status: {str(e)}"},
            status_code=500
        )

@app.get("/health")
async def health_check():
    """Enhanced health check endpoint with detailed diagnostics."""
    try:
        status_dict = url_rotator.url_status.get_all_status()
        current_time = time.time()
        
        # Calculate truly available URLs (successful within last 5 minutes)
        available_urls = 0
        recent_failures = 0
        total_requests = sum(url_rotator.request_counts.values())
        
        for status in status_dict.values():
            if (status.get('available', False) and 
                status.get('last_success') and 
                current_time - status.get('last_success', 0) < 300):
                available_urls += 1
            elif status.get('consecutive_failures', 0) > 0:
                recent_failures += 1
        
        # Determine health status
        if available_urls == 0:
            health_status = "unhealthy"
            status_code = 503
        elif available_urls < len(url_rotator.urls) * 0.5:
            health_status = "degraded"
            status_code = 200
        else:
            health_status = "healthy"
            status_code = 200
        
        health_data = {
            "status": health_status,
            "timestamp": datetime.datetime.now().isoformat(),
            "service_info": {
                "version": "1.1.0",
                "uptime_seconds": int(current_time - (getattr(health_check, 'start_time', current_time))),
                "total_requests_processed": total_requests
            },
            "endpoints": {
                "total_configured": len(url_rotator.urls),
                "currently_available": available_urls,
                "recently_failed": recent_failures,
                "availability_percentage": round((available_urls / len(url_rotator.urls)) * 100, 1) if url_rotator.urls else 0
            },
            "performance": {
                "avg_response_time": None,
                "rate_limit_status": "normal"  # Could be enhanced with actual rate limit monitoring
            }
        }
        
        # Add average response time if available
        latencies = [s.get('latency') for s in status_dict.values() if s.get('latency')]
        if latencies:
            health_data["performance"]["avg_response_time"] = round(sum(latencies) / len(latencies), 3)
        
        # Add detailed status only in debug mode
        if os.getenv("DEBUG", "false").lower() == "true":
            health_data["detailed_status"] = status_dict
        
        return JSONResponse(content=health_data, status_code=status_code)
        
    except Exception as e:
        logger.exception("Error in health_check")
        return JSONResponse(
            content={
                "status": "unhealthy",
                "error": "Health check failed",
                "timestamp": datetime.datetime.now().isoformat()
            },
            status_code=503
        )

# Initialize start time for uptime calculation
health_check.start_time = time.time()

@app.get("/v1/models")
async def list_models():
    """List available translation models/language pairs."""
    models = [
        {"id": "deepl-EN-ZH", "object": "model", "created": 1677610602, "owned_by": "deepl"},
        {"id": "deepl-EN-JA", "object": "model", "created": 1677610602, "owned_by": "deepl"},
        {"id": "deepl-EN-FR", "object": "model", "created": 1677610602, "owned_by": "deepl"},
        {"id": "deepl-EN-DE", "object": "model", "created": 1677610602, "owned_by": "deepl"},
        {"id": "deepl-EN-ES", "object": "model", "created": 1677610602, "owned_by": "deepl"},
        {"id": "deepl-ZH-EN", "object": "model", "created": 1677610602, "owned_by": "deepl"},
        {"id": "deepl-JA-EN", "object": "model", "created": 1677610602, "owned_by": "deepl"},
        {"id": "deepl-FR-EN", "object": "model", "created": 1677610602, "owned_by": "deepl"},
        {"id": "deepl-DE-EN", "object": "model", "created": 1677610602, "owned_by": "deepl"},
        {"id": "deepl-ES-EN", "object": "model", "created": 1677610602, "owned_by": "deepl"},
        {"id": "deepl-ZH", "object": "model", "created": 1677610602, "owned_by": "deepl"},
        {"id": "deepl-EN", "object": "model", "created": 1677610602, "owned_by": "deepl"},
        {"id": "deepl-JA", "object": "model", "created": 1677610602, "owned_by": "deepl"},
    ]
    
    return JSONResponse(content={
        "object": "list",
        "data": models
    })

@app.get("/")
async def root():
    """API root endpoint with service information."""
    return JSONResponse(content={
        "service": "DeepLX Translation API",
        "version": "1.1.0",
        "status": "running",
        "endpoints": {
            "translate": "/v1/chat/completions",
            "health": "/health",
            "check_urls": "/v1/check-and-export-urls",
            "url_status": "/v1/urls/status",
            "models": "/v1/models"
        },
        "documentation": "/docs"
    })

async def periodic_url_check():
    """Periodically check the availability of URLs with enhanced scheduling."""
    check_interval = int(os.getenv("CHECK_INTERVAL", 300))
    initial_delay = int(os.getenv("INITIAL_CHECK_DELAY", 30))  # Wait before first check
    
    logger.info(f"Starting periodic URL checker (interval: {check_interval}s)")
    
    # Initial delay to let service start up properly
    await asyncio.sleep(initial_delay)
    
    consecutive_failures = 0
    max_consecutive_failures = 5
    
    while True:
        try:
            logger.debug("Starting periodic URL check")
            await check_and_export_urls()
            consecutive_failures = 0  # Reset on success
            
            # Dynamic interval based on availability
            status_dict = url_rotator.url_status.get_all_status()
            available_count = sum(1 for s in status_dict.values() if s.get('available', False))
            
            # If many URLs are down, check more frequently
            if available_count < len(url_rotator.urls) * 0.5:
                dynamic_interval = min(check_interval // 2, 120)  # At least every 2 minutes
                logger.info(f"Low availability detected, using shorter interval: {dynamic_interval}s")
            else:
                dynamic_interval = check_interval
            
            await asyncio.sleep(dynamic_interval)
            
        except asyncio.CancelledError:
            logger.info("Periodic URL check cancelled")
            break
        except Exception as e:
            consecutive_failures += 1
            logger.error(f"Error in periodic URL check (failure #{consecutive_failures}): {e}")
            
            if consecutive_failures >= max_consecutive_failures:
                logger.critical(f"Too many consecutive failures ({consecutive_failures}), extending sleep time")
                await asyncio.sleep(check_interval * 2)  # Back off more aggressively
                consecutive_failures = 0  # Reset counter
            else:
                await asyncio.sleep(60)  # Standard error delay

# Enhanced server startup
if __name__ == "__main__":
    def run_server():
        port = int(os.getenv("PORT", 8000))
        host = os.getenv("HOST", "0.0.0.0")  # Changed for Docker compatibility
        workers = int(os.getenv("WORKERS", 1))
        
        # Enhanced uvicorn configuration
        config = {
            "host": host,
            "port": port,
            "log_level": log_level.lower(),
            "access_log": True,
            "use_colors": True,
            "loop": "asyncio"
        }
        
        # Add workers only if > 1 (single worker is better for this use case)
        if workers > 1:
            config["workers"] = workers
        
        logger.info(f"Starting server on {host}:{port}")
        uvicorn.run(app, **config)
    
    run_server()

	
