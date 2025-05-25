#!/usr/bin/env python3
"""
SMPTE Timecode Server Examples
Demonstrates various ways to use the SMPTE server as instances.
"""

import asyncio
import logging
from smpte_server_python import SMPTETimecodeServer, run_server_instance


class EnhancedSMPTEServer(SMPTETimecodeServer):
    """Enhanced SMPTE Server with additional features"""
    
    def __init__(self, host='localhost', port=8080):
        super().__init__(host, port)
        self.session_history = []
        self.max_history_size = 100
        self.uptime_start = asyncio.get_event_loop().time()
    
    async def create_session(self, client_id: str, data: dict):
        """Override to add session history tracking"""
        await super().create_session(client_id, data)
        
        # Add to history
        self.session_history.append({
            'timestamp': asyncio.get_event_loop().time(),
            'action': 'created',
            'client_id': client_id,
            'session_data': data
        })
        
        # Trim history
        if len(self.session_history) > self.max_history_size:
            self.session_history = self.session_history[-self.max_history_size:]
        
        self.logger.info(f"Session created by client {client_id[:8]} with framerate {data.get('framerate')}")
    
    def get_enhanced_status(self):
        """Get enhanced status with history and uptime"""
        base_status = self.get_status()
        current_time = asyncio.get_event_loop().time()
        
        return {
            **base_status,
            'session_history': self.session_history[-10:],  # Last 10 events
            'uptime_seconds': current_time - self.uptime_start
        }


async def example_1_simple_server():
    """Example 1: Simple server instance"""
    print("Example 1: Running simple server instance on port 8080")
    
    # This will run indefinitely until interrupted
    await run_server_instance(host='localhost', port=8080)


async def example_2_custom_server():
    """Example 2: Server with custom configuration"""
    print("Example 2: Running server with custom configuration on port 8081")
    
    await run_server_instance(
        host='localhost',
        port=8081,
        enable_status_reporting=True
    )


async def example_3_programmatic_server():
    """Example 3: Programmatic server control"""
    print("Example 3: Creating server with programmatic control on port 8082")
    
    server = SMPTETimecodeServer('localhost', 8082)
    
    # Create background tasks
    server_task = asyncio.create_task(server.start_server())
    
    # Status monitoring task
    async def monitor_status():
        while server.running:
            await asyncio.sleep(15)
            if server.running:
                status = server.get_status()
                if status['active_sessions'] > 0:
                    print(f"Programmatic server status: {status}")
                    for session in status['sessions']:
                        print(f"  Session {session['id'][:8]}: {session['framerate']}fps, "
                              f"{session['client_count']} clients")
    
    monitor_task = asyncio.create_task(monitor_status())
    
    try:
        # Wait for server task (runs indefinitely)
        await server_task
    except KeyboardInterrupt:
        print("Shutting down programmatic server...")
    finally:
        monitor_task.cancel()
        await server.stop_server()


async def example_4_server_cluster():
    """Example 4: Multiple server instances (cluster)"""
    print("Example 4: Running server cluster on ports 8083, 8084, 8085")
    
    cluster_ports = [8083, 8084, 8085]
    servers = []
    
    # Create server instances
    for port in cluster_ports:
        server = SMPTETimecodeServer('localhost', port)
        servers.append(server)
        print(f"Starting cluster server on port {port}")
    
    # Start all servers
    server_tasks = [asyncio.create_task(server.start_server()) for server in servers]
    
    # Cluster-wide status monitoring
    async def cluster_status_monitor():
        while any(server.running for server in servers):
            await asyncio.sleep(20)
            
            total_sessions = 0
            total_clients = 0
            
            for server in servers:
                if server.running:
                    status = server.get_status()
                    total_sessions += status['active_sessions']
                    total_clients += status['connected_clients']
            
            if total_sessions > 0 or total_clients > 0:
                print(f"Cluster status: {total_clients} total clients across {total_sessions} sessions")
    
    monitor_task = asyncio.create_task(cluster_status_monitor())
    
    try:
        # Wait for any server task to complete
        await asyncio.gather(*server_tasks, return_exceptions=True)
    except KeyboardInterrupt:
        print("Shutting down server cluster...")
    finally:
        monitor_task.cancel()
        
        # Stop all servers
        for i, server in enumerate(servers):
            print(f"Stopping server on port {cluster_ports[i]}")
            await server.stop_server()


async def example_5_enhanced_server():
    """Example 5: Enhanced server with additional features"""
    print("Example 5: Running enhanced server with session history on port 8086")
    
    server = EnhancedSMPTEServer('localhost', 8086)
    
    # Start server
    server_task = asyncio.create_task(server.start_server())
    
    # Enhanced status monitoring
    async def enhanced_status_monitor():
        while server.running:
            await asyncio.sleep(25)
            if server.running:
                status = server.get_enhanced_status()
                if status['active_sessions'] > 0:
                    print(f"Enhanced server - Uptime: {status['uptime_seconds']:.1f}s")
                    print(f"Sessions: {status['active_sessions']}, Clients: {status['connected_clients']}")
                    
                    if status['session_history']:
                        print("Recent session events:")
                        for event in status['session_history'][-3:]:  # Last 3 events
                            print(f"  {event['action']} by {event['client_id'][:8]}")
    
    monitor_task = asyncio.create_task(enhanced_status_monitor())
    
    try:
        await server_task
    except KeyboardInterrupt:
        print("Shutting down enhanced server...")
    finally:
        monitor_task.cancel()
        await server.stop_server()


async def main():
    """Main function to run examples"""
    import sys
    
    if len(sys.argv) < 2:
        print("SMPTE Server Examples")
        print("Usage: python smpte_examples_python.py <example_number>")
        print("\nAvailable examples:")
        print("  1 - Simple server instance (port 8080)")
        print("  2 - Custom configuration server (port 8081)")
        print("  3 - Programmatic server control (port 8082)")
        print("  4 - Server cluster (ports 8083, 8084, 8085)")
        print("  5 - Enhanced server with history (port 8086)")
        print("\nTo connect clients:")
        print("  python smpte_client_python.py --host localhost --port <port>")
        return
    
    example_num = sys.argv[1]
    
    examples = {
        '1': example_1_simple_server,
        '2': example_2_custom_server,
        '3': example_3_programmatic_server,
        '4': example_4_server_cluster,
        '5': example_5_enhanced_server
    }
    
    example_func = examples.get(example_num)
    if not example_func:
        print(f"Invalid example number: {example_num}")
        return
    
    print(f"Running Example {example_num}")
    print("=" * 50)
    
    try:
        await example_func()
    except KeyboardInterrupt:
        print("\nExample terminated by user")
    except Exception as e:
        print(f"Example error: {e}")


if __name__ == '__main__':
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
