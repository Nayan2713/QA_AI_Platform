import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class APIDependencyMapper:
    @staticmethod
    def extract_url_parameters(url_pattern):
        """
        Extracts named path parameters like {id} or {project_id} from a URL pattern.
        """
        return re.findall(r'\{([A-Za-z0-9_]+)\}', url_pattern)

    @classmethod
    def build_dependency_graph(cls, application):
        """
        Builds a dependency graph among discovered APIEndpoints of an application.
        Matches response keys of one endpoint to request/url parameters of another.
        """
        from core.models import APIEndpoint
        endpoints = APIEndpoint.objects.filter(application=application)
        
        nodes = []
        for ep in endpoints:
            nodes.append({
                "id": ep.id,
                "method": ep.method,
                "url_pattern": ep.url_pattern,
                "response_keys": list(ep.response_schema.keys()) if isinstance(ep.response_schema, dict) else [],
                "request_keys": list(ep.request_schema.keys()) if isinstance(ep.request_schema, dict) else []
            })
            
        links = []
        
        # Heuristic parameter mapping
        for parent in nodes:
            parent_keys = parent["response_keys"]
            if not parent_keys:
                continue
                
            for child in nodes:
                if parent["id"] == child["id"]:
                    continue
                    
                # Get parameters from URL pattern
                url_params = cls.extract_url_parameters(child["url_pattern"])
                
                # Check for matches
                matches = []
                for p_key in parent_keys:
                    # Direct name matching or standard sub-entity prefixing (e.g. 'id' matching '{project_id}')
                    # Skip common generic fields like 'status', 'success', 'message', 'created_at', 'updated_at'
                    if p_key.lower() in ['status', 'success', 'message', 'created_at', 'updated_at', 'count', 'next', 'previous']:
                        continue
                        
                    # Match url path params
                    for uparam in url_params:
                        if p_key.lower() == uparam.lower() or uparam.lower().endswith(p_key.lower()) or p_key.lower().endswith(uparam.lower()):
                            matches.append(f"url:{uparam}")
                            
                    # Match body request keys
                    for rkey in child["request_keys"]:
                        if p_key.lower() == rkey.lower() or rkey.lower().endswith(p_key.lower()) or p_key.lower().endswith(rkey.lower()):
                            matches.append(f"body:{rkey}")
                            
                if matches:
                    links.append({
                        "source": parent["id"],
                        "target": child["id"],
                        "parameters": list(set(matches))
                    })
                    
        return {
            "nodes": [
                {
                    "id": n["id"],
                    "label": f"[{n['method']}] {n['url_pattern']}"
                } for n in nodes
            ],
            "links": links
        }
