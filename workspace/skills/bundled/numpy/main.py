"""
NumPy Skill —— execute任意 numpy 代码
"""
import sys
import io
import ast
import asyncio
from typing import Dict, Any

class _TeeStream:
    """同时写入真实 stdout 和缓冲区，实现实时可见 + 仍能被收集"""
    def __init__(self, real_out, buf):
        self.real_out = real_out
        self.buf = buf
    def write(self, text):
        self.real_out.write(text)
        self.real_out.flush()
        self.buf.write(text)
    def flush(self):
        self.real_out.flush()
        self.buf.flush()
    def isatty(self):
        return False

async def run(code: str) -> Dict[str, Any]:
    captured = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = _TeeStream(old_stdout, captured)

        import numpy as np

        exec_globals = {"np": np}
        exec_locals: dict = {}

        lines = [l for l in code.strip().split("\n") if l.strip() and not l.strip().startswith("#")]
        if not lines:
            sys.stdout = old_stdout
            return {"success": True, "stdout": "", "result": "(empty code)"}

        full_code = "\n".join(lines)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: exec(full_code, exec_globals, exec_locals))

        last_result = None
        last_line = lines[-1].strip()
        try:
            parsed = ast.parse(last_line)
            if (len(parsed.body) == 1
                    and isinstance(parsed.body[0], ast.Expr)):
                val = parsed.body[0].value
                if isinstance(val, ast.Call):
                    func_name = getattr(val.func, 'id', None) or ''
                    if func_name != 'print':
                        last_result = eval(last_line, exec_globals, exec_locals)
                else:
                    last_result = eval(last_line, exec_globals, exec_locals)
        except Exception:
            pass

        sys.stdout = old_stdout
        stdout = captured.getvalue()

        result: dict = {"success": True, "stdout": stdout}

        if last_result is not None:
            if isinstance(last_result, np.ndarray):
                preview = str(last_result)
                if len(preview) > 3000:
                    preview = f"shape={last_result.shape}, dtype={last_result.dtype}\n{preview[:1000]}...\n{preview[-500:]}"
                result["result"] = preview
            else:
                result["result"] = repr(last_result)

        return result

    except Exception as e:
        sys.stdout = old_stdout
        return {"success": False, "error": f"{type(e).__name__}: {e}", "stdout": captured.getvalue()}
