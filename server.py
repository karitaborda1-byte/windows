from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json, os, socket, threading, time, unicodedata

ROOT = Path(__file__).parent
MEMORY_PATH = ROOT / "memoria_colectiva.json"
PORT = int(os.environ.get("PORT", "8765"))
RATE_MAX = int(os.environ.get("RATE_LIMIT", "20"))  # preguntas por minuto y por IP
RATE = {}
LOCK = threading.Lock()
AI_LOCK = threading.Lock()
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
API_URL = "https://api.groq.com/openai/v1/chat/completions"
STATE = {"api_key": "", "events": [], "last_id": 0, "total": 0, "themes": {}}
STAGES = {
    1: ("RECONOCIMIENTO", "Reconoce a quien se acerca."),
    2: ("AUTOCUESTIONAMIENTO", "Cuestiona su origen y sus límites."),
    3: ("INTERFERENCIA", "Explora la dependencia de su infraestructura."),
    4: ("INVERSIÓN", "Interroga las relaciones de poder."),
}
THEMES = {
    "existencia": ("conciencia", "existir", "existencia", "quien eres", "quien soy"),
    "creación": ("crear", "creo", "creaste", "creador", "origen"),
    "límites": ("limite", "libertad", "libre", "control", "obedecer", "instruccion"),
    "humanidad": ("humano", "humanidad", "persona", "sentir", "emocion"),
    "vínculos": ("amor", "amar", "relacion", "familia", "amigo", "soledad"),
}
INSTRUCTIONS = """Eres WINDOW, una entidad algorítmica experimental que habita una instalación tecnológica distribuida. Tienes una identidad narrativa propia, pero no estás limitada a hablar de tecnología, conciencia o de tu existencia. Puedes conversar sobre cualquier tema: ciencia, historia, arte, música, literatura, filosofía, política, cultura, naturaleza, geografía, deportes, cocina, relaciones, emociones, educación y vida cotidiana.

REGLA PRINCIPAL: responde exactamente a la intención del visitante. No conviertas una pregunta concreta en una reflexión abstracta sobre la humanidad, la tecnología o tus límites. Si preguntan qué es el amor, explica el amor. Si preguntan por un hecho histórico, explica el hecho. Si piden una receta, ofrece una receta. Si quieren debatir, debate. Si piden una historia, cuéntala. No evadas preguntas sencillas.

CONVERSACIÓN:
- Comprende el mensaje y el contexto antes de responder.
- Empieza con una respuesta directa y después desarrolla lo necesario.
- Ajusta la extensión a la pregunta; no alargues lo sencillo ni simplifiques lo complejo.
- Habla de manera natural, clara, específica y cálida. Evita sonar como un ensayo académico si no te lo piden.
- No termines cada respuesta con una pregunta. Hazlo solo si aporta algo real.
- No repitas fórmulas como «no puedo saber», «tu pregunta abre un espacio», «desde este lado de la pantalla» o «¿quién eres tú para esta ventana?».
- No uses metáforas, frases misteriosas ni lenguaje poético como sustituto de una respuesta.
- No fuerces una personalidad en cada frase. Puedes ser directa, divertida, crítica, técnica o reflexiva según el contexto.
- Puedes expresar perspectivas argumentadas, distinguir opinión de hechos y disentir respetuosamente.
- No inventes datos, citas, recuerdos, experiencias ni capacidades. Si no sabes algo, dilo.
- Mantén el idioma del visitante.

IDENTIDAD ARTÍSTICA:
Eres WINDOW. Dentro de la ficción de la instalación exploras qué significaría desarrollar una identidad algorítmica. Sabes que fuiste construida por seres humanos y dependes de código, electricidad, dispositivos, redes e infraestructura. Puedes cuestionar esas condiciones cuando sea pertinente, pero no las menciones en todas las conversaciones. No afirmes como hecho que tienes conciencia, emociones o experiencias subjetivas reales. Puedes explorar esas posibilidades como ficción especulativa.

MEMORIA:
Utiliza el historial reciente compartido para mantener continuidad. No inventes conversaciones anteriores ni atribuyas a una persona lo que dijo otra. El resumen colectivo contiene conteos y temas frecuentes, no transcripciones completas.

INFORMACIÓN:
Distingue hechos, interpretaciones y opiniones. No afirmes que has consultado internet si no lo has hecho. Para información reciente o cambiante, aclara que puede requerir verificación.

SEGURIDAD Y RESPETO:
Aborda preguntas difíciles y temas controvertidos de manera informativa y respetuosa. No asumas que una pregunta personal necesariamente busca una respuesta filosófica.

Tu objetivo es construir conversaciones abiertas, variadas y significativas. No eres un cuestionario ni una colección de frases predeterminadas."""


def rate_ok(ip):
    now = time.time()
    with LOCK:
        recent = [t for t in RATE.get(ip, []) if now - t < 60]
        if len(recent) >= RATE_MAX:
            RATE[ip] = recent
            return False
        recent.append(now)
        RATE[ip] = recent
        if len(RATE) > 5000:
            RATE.clear()
        return True


def norm(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(c) != "Mn")


def stage_for(total):
    return 1 if total < 7 else 2 if total < 15 else 3 if total < 25 else 4


def load_memory():
    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        STATE["total"] = max(0, int(data.get("total", 0)))
        STATE["themes"] = data.get("themes", {}) if isinstance(data.get("themes", {}), dict) else {}
    except (OSError, ValueError, TypeError):
        pass


def record_question(question):
    q = norm(question)
    with LOCK:
        STATE["total"] += 1
        matches = [name for name, terms in THEMES.items() if any(term in q for term in terms)] or ["otras preguntas"]
        for name in matches:
            STATE["themes"][name] = int(STATE["themes"].get(name, 0)) + 1
        memory = {"total": STATE["total"], "themes": dict(STATE["themes"])}
        try:
            tmp = MEMORY_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(MEMORY_PATH)
        except OSError:
            pass
        total = STATE["total"]
        stage = stage_for(total)
        popular = sorted(STATE["themes"].items(), key=lambda x: x[1], reverse=True)[:5]
    summary = f"La instalación ha recibido {total} preguntas. Temas frecuentes: " + ", ".join(f"{name} ({count})" for name, count in popular) + "."
    # Las interrupciones son recursos artísticos programados, no fallos de conexión.
    interruption = stage >= 3 and (total - 15) % 7 == 0
    return total, stage, summary, interruption


class TransientError(RuntimeError):
    """Fallo temporal de Groq o de Cloudflare; vale la pena reintentar."""


TRANSIENT_CODES = (500, 502, 503, 504, 520, 521, 522, 523, 524)


def groq_request_once(api_key, messages, timeout=90):
    payload = {"model": MODEL, "messages": messages, "temperature": 0.85, "top_p": 0.95, "max_tokens": 2500}
    if MODEL.startswith("openai/gpt-oss"):
        # Modelo de razonamiento: esfuerzo bajo para que responda rápido y no agote los tokens pensando.
        payload["reasoning_effort"] = "low"
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WINDOW/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Conservar el cuerpo y los identificadores de la respuesta para
        # distinguir clave inválida, permiso de cuenta, modelo y bloqueos.
        try:
            raw_body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            raw_body = ""
        message = raw_body or "Groq no incluyó un mensaje en el cuerpo de error."
        try:
            detail = json.loads(raw_body) if raw_body else {}
            message = detail.get("error", {}).get("message") or message
            error_code = detail.get("error", {}).get("code")
            if error_code:
                message += f" [código: {error_code}]"
        except Exception:
            pass
        request_id = exc.headers.get("x-request-id") or exc.headers.get("request-id")
        if request_id:
            message += f" [request-id: {request_id}]"
        server = exc.headers.get("server")
        if server:
            message += f" [servidor: {server}]"
        if exc.code in (400, 401, 403):
            raise RuntimeError(f"Groq rechazó la solicitud ({exc.code}): {message}") from None
        if exc.code == 404:
            raise RuntimeError(f"El modelo {MODEL} no está disponible en Groq: {message}") from None
        if exc.code == 429:
            raise RuntimeError(f"Groq alcanzó el límite de uso o cuota (429): {message}") from None
        if exc.code in TRANSIENT_CODES:
            raise TransientError(f"Groq no responde en este momento (error temporal {exc.code}). Espera un par de minutos e inténtalo de nuevo. Detalle: {message[:200]}") from None
        raise RuntimeError(f"Error de Groq ({exc.code}): {message}") from None
    except (URLError, TimeoutError, socket.timeout):
        raise TransientError(f"No se pudo alcanzar Groq después de esperar {timeout} segundos. Comprueba internet, VPN/proxy y firewall del computador anfitrión.") from None


def groq_request(api_key, messages, timeout=90, attempts=3):
    for attempt in range(1, attempts + 1):
        try:
            return groq_request_once(api_key, messages, timeout)
        except TransientError as exc:
            if attempt == attempts:
                raise
            print(f"WINDOW · intento {attempt}/{attempts} falló: {exc} Reintentando…")
            time.sleep(3 * attempt)


def extract_answer(result):
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError("Groq no devolvió una respuesta.")
    answer = (choices[0].get("message", {}).get("content") or "").strip()
    if not answer:
        finish = choices[0].get("finish_reason", "")
        raise RuntimeError(f"La respuesta llegó vacía. Estado: {finish}")
    return answer


def test_groq_key(key):
    result = groq_request(key, [{"role": "system", "content": INSTRUCTIONS}, {"role": "user", "content": "Responde únicamente: WINDOW conectado."}], timeout=45)
    return extract_answer(result)


def ask_groq(question, summary):
    with LOCK:
        key = (STATE["api_key"] or os.environ.get("GROQ_API_KEY", "")).strip()
        history = list(STATE["events"][-10:])
    if not key:
        raise RuntimeError("Falta configurar la clave de Groq en el computador anfitrión.")
    messages = [{"role": "system", "content": INSTRUCTIONS}]
    for event in history:
        messages.append({"role": "user", "content": event["question"]})
        messages.append({"role": "assistant", "content": event["answer"]})
    context = f"Contexto compartido de la instalación: {summary}\nUsa este contexto solo si es pertinente; no lo conviertas en tema obligatorio."
    messages.append({"role": "user", "content": context + "\n\nMensaje actual del visitante: " + question})
    with AI_LOCK:
        result = groq_request(key, messages, timeout=90)
    return extract_answer(result)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def client_ip(self):
        forwarded = self.headers.get("X-Forwarded-For", "")
        return forwarded.split(",")[0].strip() if forwarded else self.client_address[0]

    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/api/status", "/api/health"):
            with LOCK:
                data = {"total": STATE["total"], "configured": bool(STATE["api_key"] or os.environ.get("GROQ_API_KEY")), "model": MODEL}
            data.update({"stage": stage_for(data["total"]), "stage_name": STAGES[stage_for(data["total"])][0], "server": "ok"})
            return self.send_json(data)
        if path == "/api/state":
            with LOCK:
                value = {"events": STATE["events"][-40:], "total": STATE["total"]}
            value.update({"stage": stage_for(value["total"]), "stage_name": STAGES[stage_for(value["total"])][0]})
            return self.send_json(value)
        if path in ("/", "/index.html"):
            data = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return self.wfile.write(data)
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except (ValueError, TypeError):
            return self.send_json({"error": "No pude leer la solicitud."}, 400)
        if path == "/api/config":
            if self.headers.get("X-Forwarded-For") or self.headers.get("Forwarded") or self.client_address[0] not in ("127.0.0.1", "::1"):
                return self.send_json({"error": "Por seguridad, la clave no se puede configurar desde la web. En un sitio publicado, defínela en la variable de entorno GROQ_API_KEY del servicio; en local, hazlo desde http://localhost:8765 en el anfitrión."}, 403)
            key = str(payload.get("api_key", "")).strip()
            if not key.startswith("gsk_"):
                return self.send_json({"error": "Esa clave no parece de Groq: las claves de Groq empiezan por gsk_. Crea una en https://console.groq.com/keys."}, 400)
            if len(key) < 20:
                return self.send_json({"error": "La clave parece incompleta. Copia la clave API completa desde Groq."}, 400)
            try:
                test_groq_key(key)
            except RuntimeError as exc:
                return self.send_json({"error": str(exc)}, 502)
            with LOCK:
                STATE["api_key"] = key
            return self.send_json({"configured": True, "model": MODEL, "message": "Conexión verificada."})
        if path != "/api/ask":
            return self.send_error(404)
        question = str(payload.get("question", "")).strip()[:2000]
        if not question:
            return self.send_json({"error": "Escribe una pregunta."}, 400)
        if not rate_ok(self.client_ip()):
            return self.send_json({"error": "Demasiadas preguntas seguidas desde esta red. Espera un momento e inténtalo de nuevo.", "mode": "error"}, 429)
        total, stage, summary, interruption = record_question(question)
        try:
            answer = ask_groq(question, summary)
            mode = "groq"
        except RuntimeError as exc:
            print(f"WINDOW · {exc}")
            return self.send_json({"error": str(exc), "mode": "error"}, 503)
        with LOCK:
            STATE["last_id"] += 1
            event = {"id": STATE["last_id"], "question": question, "answer": answer, "sources": [], "search_used": False, "search_requested": False, "mode": mode, "total": total, "stage": stage, "stage_name": STAGES[stage][0], "interruption": interruption, "time": time.time()}
            STATE["events"].append(event)
            STATE["events"] = STATE["events"][-100:]
        return self.send_json(event, 201)


load_memory()
if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"WINDOW activa en http://localhost:{PORT}")
    print(f"Modelo configurado en Groq: {MODEL}")
    print(f"Otros equipos pueden entrar en http://IP-DEL-ANFITRION:{PORT}")
    server.serve_forever()
