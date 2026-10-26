import subprocess
import os
import tempfile
from pathlib import Path
import pandas as pd
import streamlit as st
from faster_whisper import WhisperModel

st.set_page_config(page_title="STARLYRICS", page_icon="✨", layout="wide")
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Righteous&family=Urbanist:wght@400;600;800&display=swap');
.stApp{background:radial-gradient(circle at 15% 10%,#ffe5f4,transparent 32%),radial-gradient(circle at 85% 20%,#e8e3ff,transparent 28%),linear-gradient(135deg,#fff9fd,#f8f5ff 55%,#fff);color:#29202d}
.hero{text-align:center;padding:1rem 0}.hero h1{font-family:Righteous,cursive;font-size:clamp(2.7rem,7vw,5rem);letter-spacing:.06em;margin:0;background:linear-gradient(90deg,#ff77c8,#fff,#b7a4ff,#ff77c8);-webkit-background-clip:text;color:transparent;-webkit-text-stroke:1px #d87bb7;filter:drop-shadow(2px 3px 0 #ead2ff)}
.hero p{letter-spacing:.18em;font-weight:800;color:#a04d91}
div[data-testid="stFileUploader"]{background:#ffffffa8;border:1px solid #f3c5e5;border-radius:18px;padding:1rem}
.stButton button{border-radius:999px;font-weight:800}
</style>
<div class="hero"><h1>STARLYRICS</h1><p>MAKE YOUR LYRICS SHINE</p><div>Tu música, tus letras, tu estilo ✦</div></div>
""", unsafe_allow_html=True)
st.caption("Karaoke palabra por palabra. En canciones cantadas, revisa los tiempos porque el reconocimiento automático puede equivocarse.")


# ---------------------------------------------------------------------------
# XTTS-v2 — clonación de voz
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
VOCES_DIR = BASE_DIR / "voces"
TMP_DIR = BASE_DIR / "tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)
XTTS_TTS = BASE_DIR / ".venv-xtts" / "bin" / "tts"
XTTS_REFERENCIA = VOCES_DIR / "mi_voz.wav"
XTTS_DIR = TMP_DIR / "xtts"
XTTS_DIR.mkdir(parents=True, exist_ok=True)


def generar_xtts(texto: str) -> bytes:
    """Genera un WAV con XTTS-v2 usando voces/mi_voz.wav."""
    descriptor, nombre_salida = tempfile.mkstemp(prefix="mi_voz_", suffix=".wav", dir=str(XTTS_DIR))
    os.close(descriptor)
    salida = Path(nombre_salida)
    try:
        if not XTTS_TTS.is_file():
            raise FileNotFoundError(f"No encuentro XTTS-v2 en {XTTS_TTS}.")
        if not XTTS_REFERENCIA.is_file():
            raise FileNotFoundError(f"No encuentro la grabación {XTTS_REFERENCIA}.")
        comando = [
            str(XTTS_TTS),
            "--model_name", "tts_models/multilingual/multi-dataset/xtts_v2",
            "--text", texto.strip(),
            "--speaker_wav", str(XTTS_REFERENCIA),
            "--language_idx", "es",
            "--out_path", str(salida),
        ]
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=300, check=False)
        if resultado.returncode != 0 or not salida.is_file() or salida.stat().st_size <= 44:
            detalle = (resultado.stderr or resultado.stdout or "XTTS-v2 no devolvió detalles")[-2500:]
            raise RuntimeError(detalle)
        return salida.read_bytes()
    finally:
        try:
            salida.unlink(missing_ok=True)
        except OSError:
            pass


def atime(t):
    t=max(0.0,float(t)); h=int(t//3600); m=int(t%3600//60); s=int(t%60); cs=int((t-int(t))*100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def esc(s):
    return str(s).replace("\\",r"\\").replace("{",r"\{").replace("}",r"\}").replace("\n",r"\N")

def make_srt(words):
    def stamp(seconds):
        seconds = max(0.0, float(seconds))
        ms = int(round((seconds - int(seconds)) * 1000))
        whole = int(seconds)
        if ms >= 1000:
            whole += 1
            ms = 0
        h = whole // 3600
        m = (whole % 3600) // 60
        sec = whole % 60
        return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

    events = []
    for index, word in enumerate(words, start=1):
        start = max(0.0, float(word["start"]))
        end = max(start + 0.12, float(word["end"]))
        # Escape SRT line breaks; text is otherwise kept as recognized.
        text = str(word["word"]).replace("\\r", " ").replace("\\n", " ").strip()
        if text:
            events.append(f"{index}\\n{stamp(start)} --> {stamp(end)}\\n{text}\\n")
    return "\\n".join(events)

def burn_in(source, subtitle_path, out, font, size, outline, color):
    # The SRT path is simple and the subtitles filter is widely supported.
    path = str(subtitle_path.resolve()).replace("\\\\", "/").replace(":", r"\\:")
    color_map = {
        "Blanco": "&H00FFFFFF",
        "Rosa pastel": "&H00F7B9E8",
        "Lila": "&H00D9B7FF",
        "Amarillo": "&H0000EFFF",
    }
    style = f"FontName={font},FontSize={size},PrimaryColour={color_map[color]},OutlineColour=&H00130B18,BorderStyle=1,Outline={outline},Shadow=1,Alignment=2,MarginV=105,Bold=1"
    vf = f"subtitles=filename='{path}':charenc=UTF-8:force_style='{style}'"
    cmd = [
        "ffmpeg", "-y", "-i", str(source), "-vf", vf,
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out),
    ]
    return subprocess.run(cmd, capture_output=True, text=True)

with st.sidebar:
    st.header("✨ Estilo")
    font=st.selectbox("Tipografía",["Arial","Arial Black","Impact","Trebuchet MS","Verdana","DejaVu Sans","Liberation Sans","Georgia","Courier New"])
    size=st.slider("Tamaño",30,100,64,2)
    outline=st.slider("Borde",1,8,3)
    base=st.selectbox("Color base",["Blanco","Rosa pastel","Lila","Amarillo"])
    highlight=st.selectbox("Color de palabra cantada",["Rosa pastel","Lila","Amarillo","Blanco"])
    per_line=st.slider("Palabras por línea",3,10,6)

pestana_karaoke, pestana_mi_voz = st.tabs(["✨ STARLYRICS", "🎙️ Mi voz IA"])

with pestana_karaoke:
    upload=st.file_uploader("1. Sube la canción o vídeo",type=["mp3","wav","m4a","aac","mp4","mov","mkv","webm"])
    if upload:
        folder=Path(tempfile.gettempdir())/"starlyrics_work"; folder.mkdir(exist_ok=True)
        source=folder/("input"+(Path(upload.name).suffix or ".mp4")); source.write_bytes(upload.getvalue())
        st.success(f"Archivo cargado: {upload.name}")

        # Mostrar siempre el archivo original que se acaba de subir.
        ext = Path(upload.name).suffix.lower()
        if ext in [".mp4", ".mov", ".mkv", ".webm"]:
            st.subheader("Vista previa del vídeo original")
            st.video(upload.getvalue())
        else:
            st.subheader("Escuchar la canción original")
            st.audio(upload.getvalue())

        c1,c2=st.columns(2)
        with c1: model_name=st.selectbox("Modelo",["small","medium","large-v3"],help="Los modelos grandes tardan más y usan más memoria.")
        with c2: language=st.selectbox("Idioma",["Detectar automáticamente","Español","Inglés","Catalán","Francés","Italiano","Portugués"])
        codes={"Español":"es","Inglés":"en","Catalán":"ca","Francés":"fr","Italiano":"it","Portugués":"pt"}
        if st.button("2. Detectar letra palabra por palabra",type="primary",use_container_width=True):
            try:
                with st.spinner("Detectando palabras y sus tiempos..."):
                    model=WhisperModel(model_name,device="cpu",compute_type="int8")
                    opts={"word_timestamps":True,"beam_size":5,"vad_filter":False}
                    if language!="Detectar automáticamente": opts["language"]=codes[language]
                    segments,info=model.transcribe(str(source),**opts)
                    rows=[]
                    for seg in segments:
                        if seg.words:
                            for w in seg.words:
                                token=(w.word or "").strip()
                                if token: rows.append({"start":round(float(w.start),3),"end":round(float(w.end),3),"word":token})
                    if rows:
                        st.session_state["sl_words"]=rows; st.session_state["sl_source"]=str(source)
                        st.success(f"{len(rows)} palabras detectadas. Idioma: {info.language}.")
                    else: st.error("No se detectaron palabras con tiempos. Prueba otro modelo.")
            except Exception as e: st.error(f"Error al reconocer la voz: {e}")

    if "sl_words" in st.session_state:
        st.subheader("3. Revisa los tiempos")
        st.write("Puedes corregir el inicio, final o texto de cada palabra.")
        frame=pd.DataFrame(st.session_state["sl_words"])
        edited=st.data_editor(frame,num_rows="dynamic",use_container_width=True,key="sl_editor",
          column_config={"start":st.column_config.NumberColumn("Inicio (s)",min_value=0.0,step=.05,format="%.3f"),
                         "end":st.column_config.NumberColumn("Final (s)",min_value=0.0,step=.05,format="%.3f"),
                         "word":st.column_config.TextColumn("Palabra")})
        if st.button("4. Crear vídeo karaoke",type="primary",use_container_width=True):
            try:
                words=[]
                for r in edited.to_dict("records"):
                    word=str(r.get("word","")).strip()
                    if word:
                        start=max(0,float(r.get("start",0))); end=max(start+.04,float(r.get("end",start+.1)))
                        words.append({"start":start,"end":end,"word":word})
                words.sort(key=lambda x:x["start"])
                if not words: st.error("No hay palabras para exportar."); st.stop()
                folder=Path(tempfile.gettempdir())/"starlyrics_work"
                subtitle=folder/"starlyrics_karaoke.srt"; out=folder/"STARLYRICS_karaoke_con_letra.mp4"
                content=make_srt(words)
                subtitle.write_text(content, encoding="utf-8")
                with st.spinner("Renderizando el vídeo con cada palabra en su momento..."):
                    result=burn_in(st.session_state["sl_source"],subtitle,out,font,size,outline,highlight)
                if result.returncode==0 and out.exists() and out.stat().st_size:
                    st.success("¡Vídeo creado!")
                    st.video(out.read_bytes(), format="video/mp4")
                    st.download_button("⬇️ Descargar STARLYRICS_karaoke_con_letra.mp4",out.read_bytes(),file_name="STARLYRICS_karaoke_con_letra.mp4",mime="video/mp4",use_container_width=True)
                else:
                    st.error("FFmpeg no ha podido crear el vídeo. Envía una captura del error.")
                    st.code((result.stderr or result.stdout or "Sin detalles")[-7000:])
                    with st.expander("Ver subtítulos generados"): st.code(content[:12000])
            except Exception as e: st.error(f"Error al crear el vídeo: {e}")

    st.divider()
    st.caption("Las voces cantadas, coros y efectos pueden causar errores de transcripción. Revisa la tabla antes de exportar.")

with pestana_mi_voz:
    st.subheader("🎙️ Mi voz IA")
    st.write("Escribe un texto y genera un WAV con tu voz mediante XTTS-v2.")
    if XTTS_REFERENCIA.is_file():
        st.caption("Grabación de referencia encontrada: `voces/mi_voz.wav`")
    else:
        st.error("No encuentro `voces/mi_voz.wav`. Coloca ahí tu grabación convertida a WAV.")

    texto_xtts = st.text_area(
        "Texto que quieres escuchar con tu voz",
        key="sl_texto_mi_voz_xtts",
        height=180,
        placeholder="Escribe aquí lo que quieres que diga tu voz…",
    )
    if st.button("✨ Generar voz con XTTS-v2", type="primary", key="sl_boton_xtts"):
        if not texto_xtts.strip():
            st.warning("Escribe un texto antes de generar el audio.")
        elif len(texto_xtts) > 2000:
            st.warning("Para esta prueba, utiliza un texto de 2.000 caracteres o menos.")
        else:
            try:
                with st.spinner("XTTS-v2 está generando tu voz. La primera vez puede tardar un poco…"):
                    audio_xtts = generar_xtts(texto_xtts)
                st.session_state["sl_audio_mi_voz_xtts"] = audio_xtts
                st.success("Audio generado.")
            except Exception as exc:
                st.error(f"No se ha podido generar la voz: {exc}")

    audio_xtts_guardado = st.session_state.get("sl_audio_mi_voz_xtts")
    if audio_xtts_guardado:
        st.audio(audio_xtts_guardado, format="audio/wav")
        st.download_button(
            "💾 Descargar audio WAV",
            data=audio_xtts_guardado,
            file_name="mi_voz_xtts.wav",
            mime="audio/wav",
            key="sl_descargar_mi_voz_xtts",
            use_container_width=True,
        )

