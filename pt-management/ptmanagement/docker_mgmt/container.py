"""Docker container management module - manages Packet Tracer containers"""

import os
import logging
import json
import socket
import subprocess
import time
from urllib.parse import quote

logger = logging.getLogger(__name__)


class DockerSocketClient:
    """Low-level Docker API client using direct Unix socket communication"""
    
    def __init__(self, socket_path='/var/run/docker.sock'):
        """Initialize with Docker socket path"""
        self.socket_path = socket_path
    
    def _send_request(self, method, path, data=None):
        """Send HTTP request to Docker socket and return (status_code, response_body)"""
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self.socket_path)
            
            # Build HTTP request
            request_line = f"{method} {path} HTTP/1.0\r\nHost: localhost\r\n"
            
            if data:
                json_data = json.dumps(data).encode('utf-8')
                request_line += f"Content-Type: application/json\r\nContent-Length: {len(json_data)}\r\n\r\n"
                sock.sendall(request_line.encode('utf-8'))
                sock.sendall(json_data)
            else:
                request_line += "\r\n"
                sock.sendall(request_line.encode('utf-8'))
            
            # Receive response
            response = b''
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
            sock.close()
            
            # Parse response
            response_str = response.decode('utf-8', errors='ignore')
            # Get status code from first line
            status_line = response_str.split('\r\n')[0]
            status_code = int(status_line.split()[1]) if len(status_line.split()) > 1 else None
            
            # Split headers and body
            parts = response_str.split('\r\n\r\n', 1)
            if len(parts) == 2:
                body = parts[1]
                try:
                    return status_code, json.loads(body)
                except json.JSONDecodeError:
                    return status_code, body
            return status_code, None
        except Exception as e:
            logger.error(f"✗ Socket request failed: {e}")
            return None, None
    
    def list_containers(self, all=False):
        """List all containers"""
        path = "/v1.41/containers/json" + ("?all=true" if all else "")
        status_code, response = self._send_request("GET", path)
        return response if isinstance(response, list) else []
    
    def create_container(self, **kwargs):
        """Create a new container"""
        # Extract container name for query parameter
        name = kwargs.pop("name", None)
        path = "/v1.41/containers/create"
        if name:
            path += f"?name={quote(name, safe='')}"
        status_code, response = self._send_request("POST", path, kwargs)
        return response
    
    def start_container(self, container_id):
        """Start a container"""
        status_code, response = self._send_request("POST", f"/v1.41/containers/{container_id}/start", {})
        # 204 No Content means success, or 200 OK
        return status_code in [200, 204]
    
    def stop_container(self, container_id):
        """Stop a container"""
        status_code, response = self._send_request("POST", f"/v1.41/containers/{container_id}/stop", {})
        # 204 No Content means success, or 200 OK
        return status_code in [200, 204]
    
    def remove_container(self, container_id, force=False):
        """Remove a container"""
        path = f"/v1.41/containers/{container_id}" + ("?force=true" if force else "")
        status_code, response = self._send_request("DELETE", path)
        return status_code in [200, 204]
    
    def get_logs(self, container_id, tail=100):
        """Get container logs"""
        path = f"/v1.41/containers/{container_id}/logs?stdout=1&stderr=1&tail={tail}"
        status_code, response = self._send_request("GET", path)
        return response
    
    def exec_create(self, container_id, cmd):
        """Create an exec instance inside a container"""
        path = f"/v1.41/containers/{container_id}/exec"
        data = {
            "Cmd": cmd if isinstance(cmd, list) else cmd.split(),
            "AttachStdout": True,
            "AttachStderr": True
        }
        status_code, response = self._send_request("POST", path, data)
        return response
    
    def exec_start(self, exec_id):
        """Start an exec instance"""
        path = f"/v1.41/exec/{exec_id}/start"
        data = {
            "Detach": False,
            "Tty": False
        }
        status_code, response = self._send_request("POST", path, data)
        return response
    
    def update_container(self, container_id, **kwargs):
        """Update container resource limits"""
        path = f"/v1.41/containers/{container_id}/update"
        status_code, response = self._send_request("POST", path, kwargs)
        return status_code in [200, 204], response


class DockerManager:
    """Manages Docker containers for Packet Tracer instances"""
    
    def __init__(self):
        """Initialize Docker client using direct socket communication"""
        self.client = None
        try:
            self.client = DockerSocketClient()
            # Test connection
            containers = self.client.list_containers()
            if containers is not None:
                logger.info(f"✓ Docker socket initialized - found {len(containers)} containers")
            else:
                logger.warning("⚠ Docker socket connection succeeded but no data returned")
        except Exception as e:
            logger.warning(f"⚠ Docker socket initialization failed: {e}")
            self.client = None
    
    def health_check(self):
        """Check if Docker socket is accessible"""
        try:
            if self.client:
                containers = self.client.list_containers()
                return containers is not None
            return False
        except Exception as e:
            logger.error(f"✗ Docker health check failed: {e}")
            return False
    
    def list_containers(self, all=False):
        """
        List all Packet Tracer containers from Docker with resource info.
        
        Args:
            all: If True, include stopped containers
        
        Returns:
            List of container dicts with keys: id, name, status, ports, image, memory, cpus
        """
        try:
            if not self.client:
                logger.error("✗ Docker client not initialized")
                return []
            
            containers_data = self.client.list_containers(all=all)
            if not isinstance(containers_data, list):
                logger.warning(f"⚠ Unexpected response type: {type(containers_data)}")
                return []
            
            containers_list = []
            for container in containers_data:
                names = container.get('Names', [])
                if isinstance(names, list) and names:
                    # Names come with leading slash, e.g. "/pt-guacd/ptvnc1" or "/ptvnc1"
                    # Extract the actual container name (last part after final slash)
                    full_name = names[0].lstrip('/')
                    # Get just the container name part
                    container_name = full_name.split('/')[-1] if '/' in full_name else full_name
                else:
                    container_name = 'unknown'
                
                # Only include ptvnc containers (instance containers)
                if isinstance(container_name, str) and container_name.startswith('ptvnc'):
                    # Get resource info
                    resources = self.get_container_resources(container_name)
                    memory = resources['memory'] if resources else 'N/A'
                    cpus = resources['cpus'] if resources else 'N/A'
                    
                    containers_list.append({
                        'id': container.get('Id', '')[:12],
                        'name': container_name,
                        'status': container.get('State', 'unknown'),
                        'ports': container.get('Ports', []),
                        'image': container.get('Image', 'unknown'),
                        'memory': memory,
                        'cpus': cpus
                    })
            
            if containers_list:
                logger.info(f"✓ Found {len(containers_list)} Packet Tracer containers")
            else:
                logger.info("ℹ No Packet Tracer containers found")
            
            return containers_list
        except Exception as e:
            logger.error(f"✗ Failed to list containers: {e}")
            return []
    
    def get_container_info(self, container_name):
        """
        Get detailed information about a container using docker inspect.
        
        Args:
            container_name: Name of the container
        
        Returns:
            Dict with container details or None
        """
        try:
            cmd = ['docker', 'inspect', container_name]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if data and len(data) > 0:
                    container = data[0]
                    ports_list = []
                    if container.get('NetworkSettings', {}).get('Ports'):
                        for port_key, port_bindings in container['NetworkSettings']['Ports'].items():
                            if port_bindings:
                                ports_list.append(f"{port_bindings[0]['HostPort']}:{port_key}")
                    
                    return {
                        'id': container.get('Id', '')[:12],
                        'name': container.get('Name', '').lstrip('/'),
                        'status': container.get('State', {}).get('Status', 'unknown'),
                        'image': container.get('Config', {}).get('Image', 'unknown'),
                        'ports': ports_list,
                        'created': container.get('Created', ''),
                        'started': container.get('State', {}).get('StartedAt', ''),
                    }
            else:
                logger.error(f"✗ Failed to inspect container {container_name}: {result.stderr}")
                return None
        except json.JSONDecodeError:
            logger.error(f"✗ Invalid JSON response for {container_name}")
            return None
        except Exception as e:
            logger.error(f"✗ Failed to get container info for {container_name}: {e}")
            return None
    
    def get_container_logs(self, container_name, tail=100):
        """
        Get container logs using Docker socket API.
        
        Args:
            container_name: Name of the container
            tail: Number of lines to retrieve
        
        Returns:
            List of log lines
        """
        try:
            if not self.client:
                logger.error("✗ Docker client not initialized")
                return []
            
            # Get logs from Docker API
            logs_data = self.client.get_logs(container_name, tail=tail)
            
            if logs_data is None:
                logger.warning(f"⚠ No logs returned for {container_name}")
                return []
            
            # Docker logs API returns raw stream data, not JSON
            # Parse it as text
            if isinstance(logs_data, str):
                # Split into lines and return
                lines = logs_data.strip().split('\n')
                return [line for line in lines if line.strip()]
            elif isinstance(logs_data, bytes):
                # Decode bytes to string
                text = logs_data.decode('utf-8', errors='ignore')
                lines = text.strip().split('\n')
                return [line for line in lines if line.strip()]
            else:
                logger.warning(f"⚠ Unexpected logs format: {type(logs_data)}")
                return []
        except Exception as e:
            logger.error(f"✗ Failed to get logs for {container_name}: {e}")
            return []
    
    def create_container(self, image, container_name, environment=None, ports=None):
        """
        Create a new container using Docker socket API.
        
        Args:
            image: Docker image name
            container_name: Name for the new container
            environment: Dict of environment variables
            ports: Dict of port mappings (e.g., {'5900': '5900'})
        
        Returns:
            Container name if successful, None otherwise
        """
        try:
            logger.info(f"Creating container {container_name}...")
            
            # Build Docker API request body
            request_data = {
                "Image": image,
                "Env": [],
                "ExposedPorts": {},
                "HostConfig": {
                    "RestartPolicy": {
                        "Name": "unless-stopped"
                    },
                    "PortBindings": {},
                    "Memory": 536870912,  # 512MB in bytes
                    "Binds": [],  # For volume mounts
                    # Don't specify NetworkMode here - use bridge (default)
                    # Container will be connected to pt-stack separately after creation
                    "Dns": ["127.0.0.1"]  # Block external DNS to prevent internet access (Packet Tracer sign-in bypass)
                },
                "Volumes": {
                    "/opt/pt": {},  # Named volume for shared Packet Tracer binary
                    "/shared": {}   # Shared files directory
                }
            }
            
            # Add environment variables
            if environment:
                for key, value in environment.items():
                    request_data["Env"].append(f"{key}={value}")
            
            # Mount shared /opt/pt volume (named volume pt_opt - reused across containers)
            # Mount shared files directory
            # CRITICAL: Use SHARED_HOST_PATH (host path) not PROJECT_ROOT (container path)
            # Docker daemon reads paths from host perspective, not from pt-management container perspective
            shared_host_path_env = os.getenv('SHARED_HOST_PATH')
            project_root_env = os.getenv('PROJECT_ROOT')
            logger.info(f"DEBUG container.py: SHARED_HOST_PATH={shared_host_path_env}, PROJECT_ROOT={project_root_env}")
            
            shared_path = shared_host_path_env if shared_host_path_env else '/run/media/kalpa/9530f1e7-4f57-4bf2-b7f2-b03a2b8d4111/PT DEv/PacketTracerWeb/shared'
            logger.info(f"DEBUG container.py: Using shared_path={shared_path}")
            
            request_data["HostConfig"]["Binds"] = [
                "pt_opt:/opt/pt",  # Named volume for Packet Tracer binary
                f"{shared_path}:/shared"  # Bind mount for shared files (MUST be host path)
            ]
            
            logger.info(f"Mounting: pt_opt:/opt/pt and {shared_path}:/shared on bridge network (will connect to pt-stack after creation)")
            
            # Add port mappings
            if ports:
                for container_port, host_port in ports.items():
                    # ExposedPorts needs port/protocol format
                    port_key = f"{container_port}/tcp"
                    request_data["ExposedPorts"][port_key] = {}
                    request_data["HostConfig"]["PortBindings"][port_key] = [{
                        "HostIp": "0.0.0.0",
                        "HostPort": str(host_port)
                    }]
            
            # Add container name to the request
            request_data["name"] = container_name
            
            # Create container via socket API
            response = self.client.create_container(**request_data)
            
            if response and "Id" in response:
                container_id = response["Id"][:12]
                
                # Start the container
                self.client.start_container(response["Id"])
                
                logger.info(f"✓ Created container {container_name} ({container_id}) on bridge network")
                return container_name
            else:
                logger.error(f"✗ Failed to create container {container_name}: {response}")
                return None
        except Exception as e:
            logger.error(f"✗ Failed to create container {container_name}: {e}")
            return None
    
    def start_container(self, container_name):
        """Start a stopped container using Docker socket API"""
        try:
            if not self.client:
                logger.error("✗ Docker client not initialized")
                return False
            
            # Get container ID first
            containers = self.client.list_containers(all=True)
            container_id = None
            for c in containers:
                names = c.get('Names', [])
                if any(name.endswith(container_name) or name.endswith('/' + container_name) for name in names):
                    container_id = c.get('Id')
                    break
            
            if not container_id:
                logger.error(f"✗ Container {container_name} not found")
                return False
            
            result = self.client.start_container(container_id)
            if result:
                logger.info(f"✓ Started container {container_name}")
                return True
            else:
                logger.error(f"✗ Failed to start container {container_name}")
                return False
        except Exception as e:
            logger.error(f"✗ Failed to start container {container_name}: {e}")
            return False
    
    def stop_container(self, container_name):
        """Stop a running container using Docker socket API"""
        try:
            if not self.client:
                logger.error("✗ Docker client not initialized")
                return False
            
            # Get container ID first
            containers = self.client.list_containers(all=True)
            container_id = None
            for c in containers:
                names = c.get('Names', [])
                if any(name.endswith(container_name) or name.endswith('/' + container_name) for name in names):
                    container_id = c.get('Id')
                    break
            
            if not container_id:
                logger.error(f"✗ Container {container_name} not found")
                return False
            
            result = self.client.stop_container(container_id)
            if result:
                logger.info(f"✓ Stopped container {container_name}")
                return True
            else:
                logger.error(f"✗ Failed to stop container {container_name}")
                return False
        except Exception as e:
            logger.error(f"✗ Failed to stop container {container_name}: {e}")
            return False
    
    def restart_container(self, container_name):
        """Restart a container using Docker socket API"""
        try:
            if not self.client:
                logger.error("✗ Docker client not initialized")
                return False
            
            # Get container ID first
            containers = self.client.list_containers(all=True)
            container_id = None
            for c in containers:
                names = c.get('Names', [])
                if any(name.endswith(container_name) or name.endswith('/' + container_name) for name in names):
                    container_id = c.get('Id')
                    break
            
            if not container_id:
                logger.error(f"✗ Container {container_name} not found")
                return False
            
            # Stop then start the container
            self.client.stop_container(container_id)
            time.sleep(1)  # Give it a moment to stop
            result = self.client.start_container(container_id)
            
            if result:
                logger.info(f"✓ Restarted container {container_name}")
                return True
            else:
                logger.error(f"✗ Failed to restart container {container_name}")
                return False
        except Exception as e:
            logger.error(f"✗ Failed to restart container {container_name}: {e}")
            return False
    
    def exec_in_container(self, container_name, cmd_list):
        """Execute a command inside a container using Docker API"""
        try:
            # Get container ID
            containers = self.list_containers()
            container_id = None
            for c in containers:
                if c.get('name') == container_name or c.get('id').startswith(container_name):
                    container_id = c.get('id')
                    break
            
            if not container_id:
                logger.error(f"✗ Container {container_name} not found for exec")
                return False
            
            # Create exec instance
            exec_result = self.client.exec_create(container_id, cmd_list)
            if not exec_result or 'Id' not in exec_result:
                logger.error(f"✗ Failed to create exec instance in {container_name}")
                return False
            
            # Start exec instance
            exec_id = exec_result['Id']
            start_result = self.client.exec_start(exec_id)
            logger.info(f"✓ Executed command in {container_name}: {' '.join(cmd_list)}")
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to exec in container {container_name}: {e}")
            return False
    
    def delete_container(self, container_name, force=False):
        """Delete a container using Docker socket API"""
        try:
            # Get container info first
            containers = self.list_containers()
            container_id = None
            for c in containers:
                if c.get('name') == container_name or c.get('id').startswith(container_name):
                    container_id = c.get('id')
                    break
            
            if not container_id:
                logger.error(f"✗ Container {container_name} not found")
                return False
            
            # Stop container if running
            try:
                response = self.client.stop_container(container_id)
                logger.info(f"Stopped container {container_name}")
            except Exception as e:
                logger.warning(f"Could not stop container: {e}")
            
            # Delete the container via socket API
            response = self.client.remove_container(container_id, force=force)
            logger.info(f"✓ Deleted container {container_name}")
            return True
            
        except Exception as e:
            logger.error(f"✗ Failed to delete container {container_name}: {e}")
            return False
    
    def update_container_resources(self, container_name, memory, cpus):
        """
        Update memory and CPU limits for a container using Docker socket API.
        
        Args:
            container_name: Name of the container
            memory: Memory limit (e.g., '512M', '1G', '2048M')
            cpus: CPU limit (e.g., '1', '2', '0.5')
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.client:
                logger.error("✗ Docker client not initialized")
                return False
            
            # Get container ID first
            containers = self.client.list_containers(all=True)
            container_id = None
            for c in containers:
                names = c.get('Names', [])
                if any(name.endswith(container_name) or name.endswith('/' + container_name) for name in names):
                    container_id = c.get('Id')
                    break
            
            if not container_id:
                logger.error(f"✗ Container {container_name} not found")
                return False
            
            # Convert memory to bytes (Docker API expects bytes)
            memory_bytes = self._parse_memory_to_bytes(memory)
            if memory_bytes is None:
                logger.error(f"✗ Invalid memory format: {memory}")
                return False
            
            # Convert CPU to nanoseconds (Docker API expects CPU quota in nanoseconds)
            cpu_nanoseconds = int(float(cpus) * 1e9)
            
            # Prepare update data
            update_data = {
                'Memory': memory_bytes,
                'MemorySwap': memory_bytes,  # Prevent OOM issues
                'NanoCpus': cpu_nanoseconds
            }
            
            # Update the container via socket API
            success, response = self.client.update_container(container_id, **update_data)
            
            if success:
                logger.info(f"✓ Updated {container_name} resources: memory={memory}, cpus={cpus}")
                return True
            else:
                logger.error(f"✗ Failed to update {container_name}: {response}")
                return False
        except Exception as e:
            logger.error(f"✗ Error updating container resources for {container_name}: {e}")
            return False
    
    def _parse_memory_to_bytes(self, memory_str):
        """
        Convert memory string to bytes.
        
        Args:
            memory_str: Memory string (e.g., '512M', '1G', '2048M')
        
        Returns:
            Memory in bytes, or None if invalid format
        """
        try:
            memory_str = memory_str.strip().upper()
            
            # Parse number and unit
            units = {'B': 1, 'K': 1024, 'M': 1024**2, 'G': 1024**3}
            
            for unit, multiplier in units.items():
                if memory_str.endswith(unit):
                    number = float(memory_str[:-len(unit)])
                    return int(number * multiplier)
            
            # If no unit, assume bytes
            return int(float(memory_str))
        except (ValueError, IndexError):
            return None
    
    def get_container_resources(self, container_name):
        """
        Get current resource limits for a container via socket API.
        
        Args:
            container_name: Name of the container
        
        Returns:
            Dict with memory and cpus info, or None if failed
        """
        try:
            if not self.client:
                logger.error("✗ Docker client not initialized")
                return None
            
            # Get container ID first
            containers = self.client.list_containers(all=True)
            container_id = None
            for c in containers:
                names = c.get('Names', [])
                if any(name.endswith(container_name) or name.endswith('/' + container_name) for name in names):
                    container_id = c.get('Id')
                    break
            
            if not container_id:
                logger.warning(f"⚠ Container {container_name} not found")
                return None
            
            # Inspect the container to get resource limits
            path = f"/v1.41/containers/{container_id}/json"
            status_code, response = self.client._send_request("GET", path)
            
            if status_code != 200 or not response:
                logger.warning(f"⚠ Failed to inspect {container_name}")
                return None
            
            # Extract resource limits
            host_config = response.get('HostConfig', {})
            memory_bytes = host_config.get('Memory', 0)
            nano_cpus = host_config.get('NanoCpus', 0)
            
            # Convert to human-readable format
            memory_str = self._format_bytes_to_memory(memory_bytes)
            cpus_str = self._format_nanoseconds_to_cpus(nano_cpus)
            
            return {
                'name': container_name,
                'memory': memory_str,
                'cpus': cpus_str,
                'memory_bytes': memory_bytes,
                'nano_cpus': nano_cpus
            }
        except Exception as e:
            logger.error(f"✗ Failed to get container resources for {container_name}: {e}")
            return None
    
    def _format_bytes_to_memory(self, bytes_value):
        """Convert bytes to human-readable memory format"""
        if bytes_value == 0:
            return "unlimited"
        
        for unit in ['G', 'M', 'K']:
            divisor = 1024 ** {'G': 3, 'M': 2, 'K': 1}[unit]
            if bytes_value >= divisor:
                return f"{bytes_value / divisor:.1f}{unit}"
        
        return f"{bytes_value}B"
    
    def _format_nanoseconds_to_cpus(self, nano_cpus):
        """Convert nanoseconds to CPU cores"""
        if nano_cpus == 0:
            return "unlimited"
        
        cpus = nano_cpus / 1e9
        if cpus == int(cpus):
            return str(int(cpus))
        return f"{cpus:.2f}"
    
    def get_stats(self):
        """
        Get aggregate statistics about containers using Docker socket API.
        
        Returns:
            Dict with total running, stopped, and resource usage
        """
        try:
            containers = self.list_containers(all=True)
            
            running = sum(1 for c in containers if c.get('status') == 'running')
            stopped = len(containers) - running
            pt_containers = sum(1 for c in containers if c.get('name', '').startswith('ptvnc'))
            
            return {
                'total': len(containers),
                'running': running,
                'stopped': stopped,
                'pt_containers': pt_containers
            }
        except Exception as e:
            logger.error(f"✗ Failed to get stats: {e}")
            return {}

