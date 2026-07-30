import json
import logging
import asyncio
import warnings
import redis.asyncio as aioredis
from django.http import StreamingHttpResponse
from django.views import View
from rest_framework_simplejwt.tokens import AccessToken

warnings.filterwarnings('ignore', message='.*StreamingHttpResponse.*')

logger = logging.getLogger(__name__)

class RealTimeEventView(View):
    async def _error_generator(self, message):
        yield f"data: {json.dumps({'type': 'auth_error', 'message': message})}\n\n"

    async def get(self, request, *args, **kwargs):
        token_str = request.GET.get('token')
        if not token_str:
            return StreamingHttpResponse(
                self._error_generator('Authentication token is required'),
                status=200,
                content_type='text/event-stream'
            )

        try:
            # Cryptographically validate Simple-JWT token
            access_token = AccessToken(token_str)
            user_id = int(access_token['user_id'])
        except Exception as e:
            logger.warning(f"SSE authentication failed: {e}")
            return StreamingHttpResponse(
                self._error_generator('Invalid token'),
                status=200,
                content_type='text/event-stream'
            )

        async def event_generator():
            from qa_engine.redis_client import get_async_redis_client
            r = get_async_redis_client()
            pubsub = r.pubsub()
            await pubsub.subscribe('qa_platform_events')

            # Send initial connection status
            yield f"data: {json.dumps({'type': 'connected', 'user_id': user_id})}\n\n"

            loop = asyncio.get_event_loop()
            last_heartbeat = loop.time()
            try:
                while True:
                    try:
                        # Non-blocking check for new messages with 1s timeout
                        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                        if message:
                            raw = message['data']
                            payload_str = raw.decode('utf-8') if isinstance(raw, bytes) else raw
                            payload = json.loads(payload_str)

                            # Deliver event only if it belongs to this user
                            event_user_id = payload.get('user_id')
                            if event_user_id is None or int(event_user_id) == user_id:
                                yield f"data: {payload_str}\n\n"

                        # Send periodic keep-alive heartbeat every 5 seconds to prevent connection drops and detect disconnects
                        now = loop.time()
                        if now - last_heartbeat > 5:
                            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                            last_heartbeat = now

                    except (aioredis.ConnectionError, aioredis.TimeoutError) as conn_err:
                        logger.warning(f"SSE Redis connection issue: {conn_err}. Reconnecting...")
                        await asyncio.sleep(1)
                        pubsub = r.pubsub()
                        await pubsub.subscribe('qa_platform_events')
                    except (BrokenPipeError, ConnectionResetError) as write_err:
                        logger.info(f"SSE client disconnected: {write_err}")
                        break
                    except Exception as loop_err:
                        logger.error(f"Error in SSE loop: {loop_err}")
                        await asyncio.sleep(1)
            except GeneratorExit:
                logger.info(f"SSE stream generator exit for user {user_id}")
            finally:
                try:
                    await pubsub.unsubscribe('qa_platform_events')
                    await pubsub.close()
                except Exception:
                    pass

        response = StreamingHttpResponse(event_generator(), content_type='text/event-stream')
        # Prevent proxy/web server buffering
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        # SSE standard headers
        response['Content-Type'] = 'text/event-stream'
        return response