"""Make the repo root importable so tests can import custom_components.*"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
