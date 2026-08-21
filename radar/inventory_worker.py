"""Neutral entry point for inventory synchronisation and import jobs.

The legacy radar.portainer_worker module remains importable for existing deployments.
"""
from .portainer_worker import main


if __name__ == "__main__":
    main()