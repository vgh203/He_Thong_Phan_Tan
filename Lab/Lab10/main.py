"""
Main entry point for Lab 10: Secure Group Multicast & ABAC Policy Simulator.
Runs the complete LKH Dynamic Rekeying and ABAC Policy Evaluation simulation.
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from simulation import run_simulation

if __name__ == "__main__":
    run_simulation()
