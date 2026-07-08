import json
import logging
import time
import redis
from django.http import StreamingHttpResponse
from django.views import View
from django.conf import settings
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

class RealTimeEventView(View):
    def get(self, request, *args, **kwargs):
        token_str = request.GET.get('token')
        if not token_str:
            return StreamingHttpResponse(
                iter([f"data: {json.dumps({'type': 'auth_error', 'message': 'Authentication token is required'})}\n\n"]),
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
                iter([f"data: {json.dumps({'type': 'auth_error', 'message': 'Invalid token'})}\n\n"]),
                status=200,
                content_type='text/event-stream'
            )

        def event_generator():
            from qa_engine.redis_client import get_redis_client
            r = get_redis_client()
            pubsub = r.pubsub()
            pubsub.subscribe('qa_platform_events')
            
            # Send initial connection status
            yield f"data: {json.dumps({'type': 'connected', 'user_id': user_id})}\n\n"
            
            last_heartbeat = time.time()
            try:
                while True:
                    try:
                        # Non-blocking check for new messages with 1s timeout
                        message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                        if message:
                            payload_str = message['data'].decode('utf-8')
                            payload = json.loads(payload_str)
                            
                            # Deliver event only if it belongs to this user
                            event_user_id = payload.get('user_id')
                            if event_user_id is None or int(event_user_id) == user_id:
                                yield f"data: {payload_str}\n\n"
                        
                        # Send periodic keep-alive heartbeat every 15 seconds to prevent connection drops
                        now = time.time()
                        if now - last_heartbeat > 15:
                            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                            last_heartbeat = now
                            
                    except (redis.ConnectionError, redis.TimeoutError) as conn_err:
                        logger.warning(f"SSE Redis connection issue: {conn_err}. Reconnecting...")
                        time.sleep(1)
                        pubsub = r.pubsub()
                        pubsub.subscribe('qa_platform_events')
                    except Exception as loop_err:
                        logger.error(f"Error in SSE loop: {loop_err}")
                        time.sleep(1)
            except GeneratorExit:
                logger.info(f"SSE stream generator exit for user {user_id}")
            finally:
                try:
                    pubsub.unsubscribe('qa_platform_events')
                    pubsub.close()
                except Exception:
                    pass

        response = StreamingHttpResponse(event_generator(), content_type='text/event-stream')
        # Prevent proxy/web server buffering
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        # SSE standard headers
        response['Content-Type'] = 'text/event-stream'
        return response
