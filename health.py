#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
健康检查模块：启动一个简单的 HTTP 服务，返回 Hello。

用于 Render 等平台部署 Web Service 时满足"必须监听端口"的要求。
不参与业务逻辑，仅作为存活探测。
"""

import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    """处理健康检查请求，任何路径都返回 Hello。"""

    def do_GET(self):
        """响应 GET 请求，返回 Hello。"""
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Hello")

    def do_HEAD(self):
        """响应 HEAD 请求，仅返回响应头。"""
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        """屏蔽默认的请求日志，避免刷屏。"""
        pass


def start_health_server() -> HTTPServer:
    """在后台线程启动健康检查 HTTP 服务。

    监听 0.0.0.0，端口读取环境变量 PORT，默认 8080。
    Render 会自动注入 PORT 环境变量。

    Returns:
        已启动的 HTTPServer 实例。
    """
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("健康检查服务已启动: http://0.0.0.0:%s", port)
    return server