"""Paquete de tests (necesario para `from tests.test_sesion import ...`).

Sin este archivo, si hay un paquete `tests` instalado en site-packages, Python
resuelve ese en lugar de esta carpeta (los paquetes regulares ganan a los
namespace packages) y la recolección falla con ModuleNotFoundError.
"""
