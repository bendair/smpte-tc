#!/usr/bin/env python3
"""
SMPTE Timecode Server
Supports multiple sessions with various framerates and concurrent client connections.
"""

import asyncio
import json
import logging
import signal
import sys
import uuid
from datetime import datetime
from typing import Dict, Set, Optional, Any
import argparse


class SMPTETimecode:
    """Represents a SMPTE timecode with hours, minutes, seconds, and frames."""
    
    def __init__(self, hours: int = 0, minutes: int = 0, seconds: int = 0, frames: int = 0):
        self.hours = hours
        self.minutes = minutes
        self.seconds = seconds
        self.frames = frames
    
    @classmethod
    def from_string(cls, timecode_str: str) -> 'SMPTETimecode':
        """Parse timecode from string format HH:MM:SS:FF"""
        parts = timecode_str.split(':')
        if len(parts) != 4:
            raise ValueError("Invalid timecode format. Use HH:MM:SS:FF")
        
        return cls(
            hours=int(parts[0]),
            minutes=int(parts[1]),
            seconds=int(parts[2]),
            frames=int(parts[3])
        )
    
    def to_string(self) -> str:
        """Convert timecode to string format HH:MM:SS:FF"""
        return f"{self.hours:02d}:{self.minutes:02d}:{self.seconds:02d}:{self.frames:02d}"
    
    def increment(self, max_frames: int):
        """Increment timecode by one frame"""
        self.frames += 1
        
        if self.frames >= max_frames:
            self.frames = 0
            self.seconds += 1
            
            if self.seconds >= 60:
                self.seconds = 0
                self.minutes += 1
                
                if self.minutes >= 60:
                    self.minutes = 0
                    self.hours += 1
                    
                    if self.hours >= 24:
                        self.hours = 0


class TimecodeSession:
    """Represents a timecode session with multiple clients."""
    
    def __init__(self, session_id: str, framerate: str, initial_timecode: SMPTETimecode, created_by: str):
        self.id = session_id
        self.framerate = framerate
        self.framerate_float = float(framerate)
        self.interval = 1.0 / self.framerate_float  # Interval in seconds
        self.timecode = initial_timecode
        self.running = False
        self.clients: Set[str] = {created_by}
        self.created_by = created_by
        self.created_at = datetime.now()
        self.task: Optional[asyncio.Task] = None
        self.server_ref = None  # Reference to server for broadcasting
    
    def get_max_frames(self) -> int:
        """Get maximum frame count for this framerate"""
        return int(self.framerate_float)
    
    async def start_timecode(self):
        """Start the timecode generation task"""
        if self.running or self.task:
            return False
        
        self.running = True
        self.task = asyncio.create_task(self._timecode_loop())
        return True
    
    async def stop_timecode(self):
        """Stop the timecode generation task"""
        if not self.running or not self.task:
            return False
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        return True
    
    async def _timecode_loop(self):
        """Main timecode generation loop"""
        try:
            while self.running:
                await asyncio.sleep(self.interval)
                if self.running:  # Check again after sleep
                    self.timecode.increment(self.get_max_frames())
                    if self.server_ref:
                        await self.server_ref.broadcast_to_session(self.id, {
                            'type': 'timecode_update',
                            'timecode': self.timecode.to_string()
                        })
        except asyncio.CancelledError:
            pass
    
    def add_client(self, client_id: str):
        """Add a client to this session"""
        self.clients.add(client_id)
    
    def remove_client(self, client_id: str):
        """Remove a client from this session"""
        self.clients.discard(client_id)
    
    def is_empty(self) -> bool:
        """Check if session has no clients"""
        return len(self.clients) == 0


class ClientConnection:
    """Represents a client connection."""
    
    def __init__(self, client_id: str, writer: asyncio.StreamWriter, address: tuple):
        self.id = client_id
        self.writer = writer
        self.address = address
        self.session_id: Optional[str] = None
        self.connected = True


class SMPTETimecodeServer:
    """SMPTE Timecode Server with session management."""
    
    SUPPORTED_FRAMERATES = {
        '23.976': 23.976,
        '24': 24.0,
        '29.97': 29.97,
        '30': 30.0,
        '50': 50.0,
        '59.94': 59.94,
        '60': 60.0
    }
    
    def __init__(self, host: str = 'localhost', port: int = 8080):
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.sessions: Dict[str, TimecodeSession] = {}
        self.clients: Dict[str, ClientConnection] = {}
        self.running = False
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    async def start_server(self):
        """Start the TCP server"""
        self.server = await asyncio.start_server(
            self.handle_client,
            self.host,
            self.port
        )
        self.running = True
        
        addr = self.server.sockets[0].getsockname()
        self.logger.info(f"SMPTE Timecode Server listening on {addr[0]}:{addr[1]}")
        self.logger.info(f"Supported framerates: {list(self.SUPPORTED_FRAMERATES.keys())}")
        
        async with self.server:
            await self.server.serve_forever()
    
    async def stop_server(self):
        """Stop the server and cleanup resources"""
        self.running = False
        
        # Stop all sessions
        for session in list(self.sessions.values()):
            await session.stop_timecode()
        
        # Close all client connections
        for client in list(self.clients.values()):
            if client.writer and not client.writer.is_closing():
                client.writer.close()
                await client.writer.wait_closed()
        
        # Stop server
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        
        self.logger.info("SMPTE Timecode Server stopped")
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a new client connection"""
        client_id = str(uuid.uuid4())
        address = writer.get_extra_info('peername')
        
        self.logger.info(f"Client connected: {client_id} from {address}")
        
        client = ClientConnection(client_id, writer, address)
        self.clients[client_id] = client
        
        try:
            # Send welcome message
            await self.send_to_client(client_id, {
                'type': 'welcome',
                'message': 'Connected to SMPTE Timecode Server',
                'supported_framerates': list(self.SUPPORTED_FRAMERATES.keys())
            })
            
            # Handle client messages
            async for line in reader:
                if not line:
                    break
                
                try:
                    message = line.decode().strip()
                    if message:
                        data = json.loads(message)
                        await self.handle_client_message(client_id, data)
                except json.JSONDecodeError:
                    await self.send_to_client(client_id, {
                        'type': 'error',
                        'message': 'Invalid JSON message'
                    })
                except Exception as e:
                    self.logger.error(f"Error handling client message: {e}")
                    await self.send_to_client(client_id, {
                        'type': 'error',
                        'message': 'Internal server error'
                    })
        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Client handler error: {e}")
        finally:
            await self.handle_client_disconnect(client_id)
    
    async def handle_client_message(self, client_id: str, data: Dict[str, Any]):
        """Handle messages from clients"""
        message_type = data.get('type')
        
        handlers = {
            'create_session': self.create_session,
            'join_session': self.join_session,
            'leave_session': self.leave_session,
            'start_timecode': self.start_timecode,
            'stop_timecode': self.stop_timecode,
            'reset_timecode': self.reset_timecode
        }
        
        handler = handlers.get(message_type)
        if handler:
            await handler(client_id, data)
        else:
            await self.send_to_client(client_id, {
                'type': 'error',
                'message': 'Unknown command'
            })
    
    async def create_session(self, client_id: str, data: Dict[str, Any]):
        """Create a new timecode session"""
        framerate = data.get('framerate')
        initial_timecode_str = data.get('initial_timecode', '00:00:00:00')
        
        if framerate not in self.SUPPORTED_FRAMERATES:
            await self.send_to_client(client_id, {
                'type': 'error',
                'message': 'Unsupported framerate'
            })
            return
        
        try:
            initial_timecode = SMPTETimecode.from_string(initial_timecode_str)
        except ValueError as e:
            await self.send_to_client(client_id, {
                'type': 'error',
                'message': f'Invalid timecode format: {e}'
            })
            return
        
        session_id = str(uuid.uuid4())
        session = TimecodeSession(session_id, framerate, initial_timecode, client_id)
        session.server_ref = self  # Set server reference for broadcasting
        
        self.sessions[session_id] = session
        
        # Update client session
        if client_id in self.clients:
            self.clients[client_id].session_id = session_id
        
        await self.send_to_client(client_id, {
            'type': 'session_created',
            'session_id': session_id,
            'framerate': framerate,
            'initial_timecode': initial_timecode.to_string()
        })
        
        self.logger.info(f"Session created: {session_id} with framerate {framerate}")
    
    async def join_session(self, client_id: str, data: Dict[str, Any]):
        """Join an existing session"""
        session_id = data.get('session_id')
        
        if session_id not in self.sessions:
            await self.send_to_client(client_id, {
                'type': 'error',
                'message': 'Session not found'
            })
            return
        
        # Leave current session if any
        await self.leave_session(client_id, {})
        
        session = self.sessions[session_id]
        session.add_client(client_id)
        
        # Update client session
        if client_id in self.clients:
            self.clients[client_id].session_id = session_id
        
        await self.send_to_client(client_id, {
            'type': 'session_joined',
            'session_id': session_id,
            'framerate': session.framerate,
            'current_timecode': session.timecode.to_string(),
            'running': session.running
        })
        
        self.logger.info(f"Client {client_id} joined session {session_id}")
    
    async def leave_session(self, client_id: str, data: Dict[str, Any]):
        """Leave current session"""
        client = self.clients.get(client_id)
        if not client or not client.session_id:
            return
        
        session = self.sessions.get(client.session_id)
        if session:
            session.remove_client(client_id)
            
            # Cleanup empty sessions
            if session.is_empty():
                await session.stop_timecode()
                del self.sessions[client.session_id]
                self.logger.info(f"Session {client.session_id} cleaned up - no clients remaining")
        
        client.session_id = None
    
    async def start_timecode(self, client_id: str, data: Dict[str, Any]):
        """Start timecode for the client's session"""
        client = self.clients.get(client_id)
        if not client or not client.session_id:
            await self.send_to_client(client_id, {
                'type': 'error',
                'message': 'Not in a session'
            })
            return
        
        session = self.sessions.get(client.session_id)
        if not session:
            await self.send_to_client(client_id, {
                'type': 'error',
                'message': 'Session not found'
            })
            return
        
        if session.running:
            await self.send_to_client(client_id, {
                'type': 'error',
                'message': 'Timecode already running'
            })
            return
        
        await session.start_timecode()
        
        await self.broadcast_to_session(session.id, {
            'type': 'timecode_started',
            'timecode': session.timecode.to_string()
        })
        
        self.logger.info(f"Timecode started for session {session.id}")
    
    async def stop_timecode(self, client_id: str, data: Dict[str, Any]):
        """Stop timecode for the client's session"""
        client = self.clients.get(client_id)
        if not client or not client.session_id:
            await self.send_to_client(client_id, {
                'type': 'error',
                'message': 'Not in a session'
            })
            return
        
        session = self.sessions.get(client.session_id)
        if not session:
            await self.send_to_client(client_id, {
                'type': 'error',
                'message': 'Session not found'
            })
            return
        
        if not session.running:
            await self.send_to_client(client_id, {
                'type': 'error',
                'message': 'Timecode not running'
            })
            return
        
        await session.stop_timecode()
        
        await self.broadcast_to_session(session.id, {
            'type': 'timecode_stopped',
            'timecode': session.timecode.to_string()
        })
        
        self.logger.info(f"Timecode stopped for session {session.id}")
    
    async def reset_timecode(self, client_id: str, data: Dict[str, Any]):
        """Reset timecode for the client's session"""
        client = self.clients.get(client_id)
        if not client or not client.session_id:
            await self.send_to_client(client_id, {
                'type': 'error',
                'message': 'Not in a session'
            })
            return
        
        session = self.sessions.get(client.session_id)
        if not session:
            await self.send_to_client(client_id, {
                'type': 'error',
                'message': 'Session not found'
            })
            return
        
        timecode_str = data.get('timecode', '00:00:00:00')
        
        try:
            new_timecode = SMPTETimecode.from_string(timecode_str)
            session.timecode = new_timecode
            
            await self.broadcast_to_session(session.id, {
                'type': 'timecode_reset',
                'timecode': session.timecode.to_string()
            })
            
            self.logger.info(f"Timecode reset for session {session.id} to {timecode_str}")
        
        except ValueError as e:
            await self.send_to_client(client_id, {
                'type': 'error',
                'message': f'Invalid timecode format: {e}'
            })
    
    async def send_to_client(self, client_id: str, message: Dict[str, Any]):
        """Send a message to a specific client"""
        client = self.clients.get(client_id)
        if client and client.connected and client.writer and not client.writer.is_closing():
            try:
                data = json.dumps(message) + '\n'
                client.writer.write(data.encode())
                await client.writer.drain()
            except Exception as e:
                self.logger.error(f"Error sending to client {client_id}: {e}")
                await self.handle_client_disconnect(client_id)
    
    async def broadcast_to_session(self, session_id: str, message: Dict[str, Any]):
        """Broadcast a message to all clients in a session"""
        session = self.sessions.get(session_id)
        if not session:
            return
        
        for client_id in list(session.clients):
            await self.send_to_client(client_id, message)
    
    async def handle_client_disconnect(self, client_id: str):
        """Handle client disconnection"""
        await self.leave_session(client_id, {})
        
        client = self.clients.get(client_id)
        if client:
            client.connected = False
            if client.writer and not client.writer.is_closing():
                client.writer.close()
                try:
                    await client.writer.wait_closed()
                except:
                    pass
            del self.clients[client_id]
        
        self.logger.info(f"Client disconnected: {client_id}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get server status information"""
        return {
            'host': self.host,
            'port': self.port,
            'active_sessions': len(self.sessions),
            'connected_clients': len(self.clients),
            'sessions': [
                {
                    'id': session.id,
                    'framerate': session.framerate,
                    'timecode': session.timecode.to_string(),
                    'running': session.running,
                    'client_count': len(session.clients),
                    'created_at': session.created_at.isoformat()
                }
                for session in self.sessions.values()
            ]
        }


async def run_server_instance(host: str = 'localhost', port: int = 8080, enable_status_reporting: bool = True):
    """Run a server instance with optional status reporting"""
    server = SMPTETimecodeServer(host, port)
    
    # Status reporting task
    status_task = None
    if enable_status_reporting:
        async def status_reporter():
            while server.running:
                await asyncio.sleep(30)
                if server.running:
                    status = server.get_status()
                    if status['active_sessions'] > 0 or status['connected_clients'] > 0:
                        server.logger.info(
                            f"Status: {status['connected_clients']} clients, "
                            f"{status['active_sessions']} sessions"
                        )
        
        status_task = asyncio.create_task(status_reporter())
    
    # Graceful shutdown handling
    def signal_handler():
        server.logger.info("Received shutdown signal")
        asyncio.create_task(shutdown())
    
    async def shutdown():
        if status_task:
            status_task.cancel()
        await server.stop_server()
    
    # Setup signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
    
    try:
        await server.start_server()
    except KeyboardInterrupt:
        pass
    finally:
        await shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SMPTE Timecode Server')
    parser.add_argument('--host', default='localhost', help='Server host (default: localhost)')
    parser.add_argument('--port', type=int, default=8080, help='Server port (default: 8080)')
    parser.add_argument('--no-status', action='store_true', help='Disable status reporting')
    
    args = parser.parse_args()
    
    print("SMPTE Timecode Server (Python)")
    print("==============================")
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"Status Reporting: {not args.no_status}")
    print()
    
    try:
        asyncio.run(run_server_instance(
            host=args.host,
            port=args.port,
            enable_status_reporting=not args.no_status
        ))
    except KeyboardInterrupt:
        print("\nShutdown complete")
    except Exception as e:
        print(f"Server error: {e}")
        sys.exit(1)
