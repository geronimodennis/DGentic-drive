"""DGentic main entry point."""
import asyncio
import sys
from config.settings import get_settings
from config.logging_config import configure_logging
from core.orchestrator import get_orchestrator, run_orchestrator
from api.app import app
from loguru import logger

# Configure logging
configure_logging()


async def main():
    """Main entry point."""
    logger.info("Starting DGentic Advanced Autonomous AI Agent Platform")
    
    settings = get_settings()
    logger.info(f"Environment: {settings.environment.value}")
    logger.info(f"Permission Mode: {settings.permission_mode.value}")
    
    # Initialize orchestrator
    orchestrator = get_orchestrator()
    logger.info(f"Orchestrator initialized: {orchestrator.id}")
    
    # Get available agents
    agent_pool = orchestrator.agent_pool
    agents = agent_pool.list_agents()
    logger.info(f"Available agents: {len(agents)}")
    for agent in agents:
        logger.info(f"  - {agent.name} ({agent.role.value})")
    
    # Start processing loop in background
    logger.info("Starting task processing loop...")
    
    try:
        # Run orchestrator processing loop
        await orchestrator.start_processing_loop()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        orchestrator.stop_processing()
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        raise
    finally:
        # Cleanup
        logger.info("Shutting down DGentic")
        
        # Save memory
        memory = orchestrator.memory_system
        memory.save()
        logger.info("Memory system persisted")


def run_api_server():
    """Run the FastAPI server."""
    import uvicorn
    
    settings = get_settings()
    logger.info(f"Starting FastAPI server on {settings.api_host}:{settings.api_port}")
    
    uvicorn.run(
        "api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        # Run API server
        run_api_server()
    else:
        # Run orchestrator
        asyncio.run(main())
