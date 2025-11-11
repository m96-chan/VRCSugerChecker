"""
WASAPI Process Loopback Native Extension のビルドスクリプト
"""
from setuptools import setup, Extension
import sys

# C++拡張モジュールの定義
wasapi_extension = Extension(
    'wasapi_process_loopback_native',
    sources=['src/modules/audio/wasapi_process_loopback_native.cpp'],
    include_dirs=[],
    libraries=['ole32', 'uuid', 'propsys'],
    extra_compile_args=['/std:c++20', '/EHsc', '/utf-8'] if sys.platform == 'win32' else [],
    language='c++'
)

setup(
    name='wasapi_process_loopback_native',
    version='1.0.0',
    description='WASAPI Process Loopback Native Extension for VRChat Audio Capture',
    ext_modules=[wasapi_extension],
    zip_safe=False,
)
