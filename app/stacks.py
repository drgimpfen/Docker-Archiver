"""
Stack discovery and validation.
"""
import os
import glob
import subprocess
from pathlib import Path


def get_own_container_mounts():
    """
    Get bind mount paths from our own container.
    Returns list of container paths that are bind-mounted (not named volumes).
    These are potential stack directories.
    """
    try:
        # Get our own container ID from /proc/self/cgroup
        with open('/proc/self/cgroup', 'r') as f:
            for line in f:
                if 'docker' in line or 'containerd' in line:
                    # Extract container ID from cgroup path
                    parts = line.strip().split('/')
                    for part in reversed(parts):
                        if len(part) >= 12:  # Docker container IDs are at least 12 chars
                            container_id = part
                            break
                    break
        
        if not container_id:
            # Fallback: try to get from hostname
            with open('/proc/sys/kernel/hostname', 'r') as f:
                hostname = f.read().strip()
                if len(hostname) >= 12:
                    container_id = hostname
        
        if not container_id:
            return []
            
        # Inspect our own container
        result = subprocess.run(
            ['docker', 'inspect', container_id],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        inspect_data = json.loads(result.stdout)
        if not inspect_data:
            return []
        
        container_data = inspect_data[0]
        mounts = container_data.get('Mounts', [])
        
        bind_mounts = []
        for mount in mounts:
            mount_type = mount.get('Type', '')
            if mount_type == 'bind':
                destination = mount.get('Destination', '')
                # Skip system mounts and our own archives mount
                if (destination and 
                    not destination.startswith('/var/') and
                    not destination.startswith('/etc/') and
                    not destination.startswith('/usr/') and
                    not destination.startswith('/proc/') and
                    not destination.startswith('/sys/') and
                    destination != '/archives' and
                    destination != '/var/run/docker.sock'):
                    bind_mounts.append(destination)
        
        return bind_mounts
        
    except Exception as e:
        # Silently fail - we'll use default paths
        return []


def get_stack_mount_paths():
    """
    Get container paths where stacks should be searched.
    Automatically detected from our own container's bind mounts.
    Returns list of container paths to search in.
    """
    # Auto-detect from our own container mounts
    auto_detected = get_own_container_mounts()
    if auto_detected:
        return auto_detected
    
    # Final fallback: default path
    return ["/opt/stacks"]


LOCAL_MOUNT_BASE = '/local'  # Fallback for backward compatibility


def discover_stacks():
    """
    Discover stacks from configured mount directories.
    Searches max 1 level deep for compose.y(a)ml or docker-compose.y(a)ml files.
    Returns list of dicts with stack info: {name, path, compose_file, mount_source}
    """
    stacks = []
    
    # Get configured mount paths
    mount_paths = get_stack_mount_paths()
    
    for mount_base in mount_paths:
        mount_path = Path(mount_base)
        if not mount_path.exists():
            continue
        
        mount_name = mount_path.name
        
        # Check if mount_path itself contains a compose file (direct stack mount)
        compose_file = find_compose_file(mount_path)
        if compose_file:
            stacks.append({
                'name': mount_name,
                'path': str(mount_path),
                'compose_file': compose_file,
                'mount_source': mount_name
            })
        else:
            # Search one level deeper for stacks
            try:
                for stack_dir in mount_path.iterdir():
                    if not stack_dir.is_dir():
                        continue
                    
                    compose_file = find_compose_file(stack_dir)
                    if compose_file:
                        stacks.append({
                            'name': stack_dir.name,
                            'path': str(stack_dir),
                            'compose_file': compose_file,
                            'mount_source': mount_name
                        })
            except (OSError, PermissionError):
                # Skip directories we can't read
                continue
    
    # Fallback to old /local method for backward compatibility
    if not stacks and os.path.exists(LOCAL_MOUNT_BASE):
        for mount_dir in Path(LOCAL_MOUNT_BASE).iterdir():
            if not mount_dir.is_dir():
                continue
            
            mount_name = mount_dir.name
            
            # Check if mount_dir itself contains a compose file (direct stack mount)
            compose_file = find_compose_file(mount_dir)
            if compose_file:
                stacks.append({
                    'name': mount_name,
                    'path': str(mount_dir),
                    'compose_file': compose_file,
                    'mount_source': mount_name
                })
            else:
                # Search one level deeper for stacks
                for stack_dir in mount_dir.iterdir():
                    if not stack_dir.is_dir():
                        continue
                    
                    compose_file = find_compose_file(stack_dir)
                    if compose_file:
                        stacks.append({
                            'name': stack_dir.name,
                            'path': str(stack_dir),
                            'compose_file': compose_file,
                            'mount_source': mount_name
                        })
    
    return sorted(stacks, key=lambda x: x['name'])
                        'mount_source': mount_name
                    })
    
    return sorted(stacks, key=lambda x: x['name'])


def find_compose_file(directory):
    """
    Find compose file in directory.
    Looks for: compose.yml, compose.yaml, docker-compose.yml, docker-compose.yaml
    Returns filename if found, None otherwise.
    """
    compose_files = [
        'compose.yml',
        'compose.yaml',
        'docker-compose.yml',
        'docker-compose.yaml'
    ]
    
    for filename in compose_files:
        filepath = Path(directory) / filename
        if filepath.is_file():
            return filename
    
    return None


def validate_stack(stack_path):
    """
    Validate that a stack directory exists and contains a compose file.
    Returns (valid: bool, error_message: str)
    """
    path = Path(stack_path)
    
    if not path.exists():
        return False, f"Stack directory does not exist: {stack_path}"
    
    if not path.is_dir():
        return False, f"Stack path is not a directory: {stack_path}"
    
    compose_file = find_compose_file(path)
    if not compose_file:
        return False, f"No compose file found in {stack_path}"
    
    return True, None


def get_stack_info(stack_path):
    """Get detailed info about a stack."""
    path = Path(stack_path)
    compose_file = find_compose_file(path)
    
    return {
        'name': path.name,
        'path': str(path),
        'compose_file': compose_file,
        'valid': compose_file is not None
    }
