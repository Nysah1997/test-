#!/usr/bin/env python3
"""
Archivo principal alternativo para hosts que buscan main.py
Este archivo simplemente importa y ejecuta bot.py
"""

import os
import sys
import asyncio

# Añadir el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    try:
        print("🔥 Iniciando bot desde main.py...")
        import bot
        print("✅ Bot importado correctamente")
    except KeyboardInterrupt:
        print("🛑 Bot detenido por el usuario")
    except Exception as e:
        print(f"❌ Error crítico: {e}")
        print("📋 Verifica tu configuración en config.json")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)