import logging
import threading
import webbrowser

import pystray
import uvicorn
from PIL import Image, ImageDraw
from watchdog.observers import Observer

from judgman.api.server import create_app
from judgman.config import Settings
from judgman.core.analyzer import Analyzer
from judgman.core.scanner import ReadOnlyScanner

logger = logging.getLogger("judgman")


def _tray_image() -> Image.Image:
    image = Image.new("RGB", (64, 64), "#14213d")
    draw = ImageDraw.Draw(image)
    draw.ellipse((12, 12, 52, 52), fill="#fca311")
    draw.text((25, 21), "J", fill="#14213d")
    return image


def serve(settings: Settings | None = None) -> None:
    """Inicia el monitor pasivo: scanner, API local, navegador y bandeja."""
    logging.basicConfig(level=logging.INFO)
    settings = settings or Settings()
    analyzer = Analyzer(
        model=settings.model,
        api_key=settings.api_key.get_secret_value(),
    )
    scanner = ReadOnlyScanner(
        settings.workspace,
        analyzer=analyzer.analyze,
        max_file_bytes=settings.max_file_bytes,
    )
    observer = Observer()
    observer.schedule(scanner, str(settings.workspace), recursive=True)
    app = create_app(settings, scanner, analyzer=analyzer)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=settings.host,
            port=settings.port,
            log_level="info",
        )
    )

    server_thread = threading.Thread(
        target=server.run,
        name="judgman-api",
        daemon=True,
    )
    scanner.start()
    observer.start()
    server_thread.start()
    logger.info("Judgman Mike disponible en http://%s:%s", settings.host, settings.port)
    webbrowser.open(f"http://{settings.host}:{settings.port}")

    def open_app(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        webbrowser.open(f"http://{settings.host}:{settings.port}")

    def stop_app(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        observer.stop()
        server.should_exit = True
        _icon.stop()

    icon = pystray.Icon(
        "judgman-mike",
        _tray_image(),
        "Judgman Mike",
        menu=pystray.Menu(
            pystray.MenuItem("Abrir Judgman", open_app),
            pystray.MenuItem("Salir", stop_app),
        ),
    )
    try:
        icon.run()
    finally:
        observer.stop()
        observer.join(timeout=5)
        scanner.stop()
        server.should_exit = True
        server_thread.join(timeout=5)


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
