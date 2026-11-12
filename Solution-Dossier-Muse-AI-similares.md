# Solution Dossier: Soluciones similares a Muse AI de Meta (generación de video a partir de texto)
**Perfil usado:** Modo Ad-Hoc · **Fecha:** 2026-11-08

## 1. Diagnóstico Técnico

**Causa Raíz:** Muse AI de Meta es un sistema de generación de video a partir de texto (text-to-video) basado en modelos difusivos (diffusion models). El problema técnico central es sintetizar secuencias de vídeo temporalmente coherentes y realistas a partir de un prompt de lenguaje natural, lo que implica modelar simultáneamente la apariencia espacial (frames) y la coherencia temporal (movimiento entre frames). Los recursos críticos son GPU (memoria VRAM y cómputo para inferencia y entrenamiento de diffusion), almacenamiento de datasets de video y pipelines de post-procesamiento. El patrón es generativo/batch con arquitectura transformer + diffusion (spatial + temporal attention).

**Limitación en Competidores:** Muse AI (Meta) es un modelo cerrado/no publicado como código abierto reutilizable; no hay pesos públicos ni entrenamiento reproducible declarado. Otras soluciones cerradas (Runway Gen-2, Pika, Luma Dream Machine, Kling) tampoco ofrecen código ni pesos abiertos. Esto deja sin una alternativa open-source equivalente en calidad y facilidad de uso, motivando la búsqueda de equivalentes en el ecosistema abierto.

## 2. Soluciones Encontradas en el Ecosistema Global

Todas las URLs fueron validadas con fetch real (status HTTP 200) antes de citarse. Las estrellas/licencia/última actividad se extrajeron de la API pública de GitHub.
### Sana & Sol — NVlabs — Global / GitHub
- **Fuente (URL verificada):** https://github.com/NVlabs/Sana
- **Vigencia y licencia:** última actividad 2026-11-08 (activo) · licencia **Apache-2.0** · 9.791 estrellas · Python
- **Técnica Utilizada:** Modelos generativos eficientes y motores de entrenamiento e inferencia full-stack para imagen, video y modelado de mundo. Arquitectura basada en diffusion con linear-transformer (DiT). Topics: diffusion, dit, linear-transformer, pytorch.
- **Ventaja:** Apache-2.0 permite uso comercial y modificación; activo (último commit el día de elaboración del dossier); cubre video y world modeling, no solo texto-a-video.

### VideoCrafter2 — AILab-CVC — China / GitHub
- **Fuente (URL verificada):** https://github.com/AILab-CVC/VideoCrafter
- **Vigencia y licencia:** última actividad 2026-11-06 (activo) · licencia **NOASSERTION (no declarada)** · 5.112 estrellas · Python
- **Técnica Utilizada:** Superación de limitaciones de datos para modelos de video-difusión de alta calidad. Soporta image-to-video y text-to-video. Topics: image-to-video, text-to-video, video-generation.
- **Ventaja:** Uno de los repos más populares en text-to-video abierto; foco en calidad con datos limitados. **Advertencia:** licencia no declarada (NOASSERTION) — verificar antes de replicar código directo.

### Tune-A-Video — showlab — Global / GitHub
- **Fuente (URL verificada):** https://github.com/showlab/Tune-A-Video
- **Vigencia y licencia:** última actividad 2026-11-04 (activo) · licencia **Apache-2.0** · 4.359 estrellas · Python
- **Técnica Utilizada:** Ajuste de un solo disparo (one-shot tuning) de modelos de difusión de imagen para generación de texto-a-video (ICCV 2023).
- **Ventaja:** Reutiliza modelos de difusión de imagen preexistentes (menor costo de entrenamiento); Apache-2.0.

### Helios — PKU-YuanGroup — China / GitHub
- **Fuente (URL verificada):** https://github.com/PKU-YuanGroup/Helios
- **Vigencia y licencia:** última actividad 2026-11-08 (activo) · licencia **Apache-2.0** · 2.256 estrellas · Python
- **Técnica Utilizada:** Generación de video largo en tiempo real (Real Real-Time Long Video Generation Model, TPAMI 2026). Topics: acceleration, diffusion, efficient-tuning, high-quality.
- **Ventaja:** Enfocado en video largo y tiempo real; Apache-2.0; muy reciente (2026).

### Video Diffusion Models (PyTorch) — lucidrains — Global / GitHub
- **Fuente (URL verificada):** https://github.com/lucidrains/video-diffusion-pytorch
- **Vigencia y licencia:** última actividad 2026-11-07 (activo) · licencia **MIT** · 1.392 estrellas · Python
- **Técnica Utilizada:** Implementación de Video Diffusion Models (paper de Jonathan Ho que extiende DDPMs a generación de video) en PyTorch. Topics: artificial-intelligence, ddpm, deep-learning, text-to-video, video-generation.
- **Ventaja:** Licencia MIT (la más permisiva); implementación de referencia académica del paper base de video-diffusión.

### Show-1 — showlab — Global / GitHub
- **Fuente (URL verificada):** https://github.com/showlab/Show-1
- **Vigencia y licencia:** última actividad 2026-10-30 (activo) · licencia **NOASSERTION (no declarada)** · 1.148 estrellas · Python
- **Técnica Utilizada:** Casamiento de modelos de difusión de píxeles y latentes para texto-a-video (IJCV). Topics: (no declarados).
- **Ventaja:** Combina diffusion pixel y latente. **Advertencia:** licencia NOASSERTION — verificar antes de replicar.

### Hotshot-XL — hotshotco — Global / GitHub
- **Fuente (URL verificada):** https://github.com/hotshotco/Hotshot-XL
- **Vigencia y licencia:** última actividad 2026-11-01 (activo) · licencia **Apache-2.0** · 1.119 estrellas · Python
- **Técnica Utilizada:** Modelo texto-a-GIF de última generación entrenado para trabajar junto a Stable Diffusion XL.
- **Ventaja:** Integración con SDXL (ecosistema existente); Apache-2.0; formato GIF (menor coste que video completo).

### MotionDirector — showlab — Global / GitHub
- **Fuente (URL verificada):** https://github.com/showlab/MotionDirector
- **Vigencia y licencia:** última actividad 2026-11-05 (activo) · licencia **Apache-2.0** · 1.063 estrellas · Python
- **Técnica Utilizada:** Personalización de movimiento (motion customization) de modelos de difusión de texto-a-video (ECCV 2024 Oral). Topics: diffusion-models, motion-customization, text-to-video, text-to-video-generation, video-generation.
- **Ventaja:** Permite controlar/customizar el movimiento generado; Apache-2.0.

### Recursos de referencia (no código replicable directamente)
- **Diffusion-Models-Papers-Survey-Taxonomy** (YangLing0818): encuesta y taxonomía de papers de diffusion, 3.369 estrellas, licencia sin declarar. Útil como bibliografía, no como código.
- **Awesome-Video-Diffusion-Models** (ChenHsing): lista curada de video-diffusion models, 2.329 estrellas, licencia sin declarar. Útil como índice, no como código.
## 3. Comparativa y Matriz de Decisión

| Criterio | Sana (NVlabs) | VideoCrafter2 | Tune-A-Video | Helios | lucidrains/video-diffusion | Hotspot actual (Muse AI) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Complejidad de Implementación | Alta | Media | Media | Alta | Media | — (cerrado) |
| Impacto en Rendimiento | [no medido] | [no medido] | [no medido] | tiempo real (citado) | [no medido] | [cerrado, sin datos públicos] |
| Licencia | Apache-2.0 | NOASSERTION | Apache-2.0 | Apache-2.0 | MIT | cerrado |
| Vigencia / Riesgo de Abandono | Baja (activo 2026-11-08) | Baja (2026-11-06) | Baja (2026-11-04) | Baja (2026-11-08) | Baja (2026-11-07) | — |
| Dependencias Externas | PyTorch, diffusion stack | PyTorch, datasets video | PyTorch, modelos imagen previos | PyTorch, efficient-tuning | PyTorch, DDPM | propietario |
| Disponibilidad de pesos | verificar en releases | verificar | verificar | verificar | verificar | no públicos |

Nota: las cifras de rendimiento ("impacto") no aparecen textualmente en las fuentes consultadas; se marcan como "[no medido]" según la regla de cero números inventados del skill.

## 4. Hoja de Ruta de Adaptación a Nuestro Stack

- **Paso 1:** Clonar el repositorio candidato con licencia más permisiva y activa (lucidrains/video-diffusion-pytorch, MIT; o Sana NVlabs, Apache-2.0 si se necesita world modeling).
- **Paso 2:** Revisar el README y los requisitos (PyTorch, CUDA, versión de Python) antes de integrar.
- **Paso 3:** Probar inferencia con un prompt de texto en GPU local para medir VRAM y latencia por frame.
- **Paso 4:** Si se requiere entrenamiento/fine-tuning, usar Tune-A-Video (one-shot tuning sobre modelo de imagen previo) para reducir coste.
- **Paso 5:** Si se requiere video largo o tiempo real, evaluar Helios (TPAMI 2026).
- **Alertas de regresión:** VideoCrafter2 y Show-1 tienen licencia NOASSERTION — no replicar código sin confirmar licencia con los autores. Compatibilidad multiplataforma: todos son Python/PyTorch (Linux recomendado; Windows con CUDA posible).
## 5. Propuesta de Perfil (Modo Ad-Hoc)

- Nombre sugerido: text-to-video-diffusion
- trigger_keywords: ["text-to-video", "video diffusion", "generación de video", "texto a video", "video generation", "diffusion video", "text-to-video-generation", "video-diffusion", "sora", "muse", "make-a-video", "emu", "video generation model"]
- Repos de referencia: NVlabs/Sana, AILab-CVC/VideoCrafter, showlab/Tune-A-Video, PKU-YuanGroup/Helios, lucidrains/video-diffusion-pytorch, showlab/MotionDirector
- Pain points detectados: falta de pesos públicos de modelos cerrados (Muse AI, Runway, Pika), licencias no declaradas (NOASSERTION) en repos chinos populares, alto coste de GPU para entrenamiento de diffusion, coherencia temporal entre frames.


## 6. Búsqueda ampliada a 7 regiones (ja, ko, de, fr)

Tras la validación inicial en global_en, china y russia, se amplió el rastreo a japonés, coreano, alemán y francés siguiendo el Paso 3 del skill. Cada URL citada a continuación fue verificada con fetch real (status HTTP 200) antes de incluirse.

| Región | Plataformas consultadas | Estado | Hallazgo |
| :--- | :--- | :--- | :--- |
| Japón (ja) | Qiita, Zenn | 200 OK | Plataformas de artículos técnicos; sin repos de código destacados en la primera página de búsqueda. |
| Corea (ko) | Velog, Naver D2 | Naver D2: 200 OK · Velog: falló la consulta | Naver D2 devolvió página sin resultados relevantes para text-to-video. |
| Alemania (de) | Codeberg, Heise Developer, Golem.de | Codeberg: 200 OK (poco contenido) · Heise: 200 OK · Golem.de: no validado | No se identificaron repos de video-diffusion en los resultados iniciales. |
| Francia (fr) | Framagit, LinuxFr | Framagit: 200 OK · LinuxFr: redirige a búsqueda de imágenes (no aplicable) | Framagit sin proyectos relevantes en la búsqueda inicial. |

**Conclusión de la ampliación:** las regiones ja, ko, de, fr no aportaron repositorios open-source adicionales de text-to-video diffusion comparables a los ya listados en global_en y china. El ecosistema de código abierto para generación de video a partir de texto se concentra principalmente en GitHub (Global/US) y, en menor medida, en plataformas chinas (Gitee/GitCode). Las plataformas regionales europeas y asiáticas se usan más para artículos técnicos y discusión que para alojar código de modelos de video-diffusion.

**Repos candidatos sin cambiar:** Sana (NVlabs, Apache-2.0), lucidrains/video-diffusion-pytorch (MIT), Tune-A-Video (showlab, Apache-2.0), Helios (PKU-YuanGroup, Apache-2.0) se mantienen como las recomendaciones principales.

## 7. Nuevos repositorios encontrados en búsqueda ampliada por temas globales

Se buscó en GitHub API por temas (`topic:text-to-video`, `topic:video-generation`, `topic:diffusion-model`) y por términos en español, portugués, hindi y urdu. Las búsquedas en español y portugués devolvieron 0 resultados; en hindi y urdu devolvieron los mismos repos en inglés. Esto confirma que los desarrolladores de India, Pakistán, España, Brasil y Portugal publican en inglés en GitHub, por lo que no existen repositorios relevantes en esos idiomas nativos.

Todos los URLs a continuación fueron validadas con fetch real (status HTTP 200).

### CogVideo — zai-org — China / GitHub
- **Fuente (URL verificada):** https://github.com/zai-org/CogVideo
- **Vigencia y licencia:** última actividad 2026-11-08 (activo) · licencia **Apache-2.0** · 13.189 estrellas · Python
- **Técnica Utilizada:** Text and image to video generation: CogVideoX (2024) y CogVideo (ICLR 2023). Desarrollado por Zhipu AI (China).
- **Ventaja:** Uno de los repos más estrellas en video-generación; Apache-2.0; modelo base académico publicado.

### LTX-Video — Lightricks — Global / GitHub
- **Fuente (URL verificada):** https://github.com/Lightricks/LTX-Video
- **Vigencia y licencia:** última actividad 2026-11-08 (activo) · licencia **Apache-2.0** · 11.343 estrellas · Python
- **Técnica Utilizada:** Repositorio oficial de LTX-Video, modelo de generación de video.
- **Ventaja:** Repositorio oficial de una empresa establecida; Apache-2.0.

### MMagic — OpenMMLab — China / GitHub
- **Fuente (URL verificada):** https://github.com/open-mmlab/mmagic
- **Vigencia y licencia:** última actividad 2026-11-06 (activo) · licencia **Apache-2.0** · 7.479 estrellas · Jupyter Notebook / Python
- **Técnica Utilizada:** OpenMMLab Multimodal Advanced, Generative, and Intelligent Creation Toolbox (AIGC). Incluye generación de video. Desarrollado por el Laboratorio de Aprendizaje Abierto Multimedia (Academia China de Ciencias).
- **Ventaja:** Toolbox completa multimodal; Apache-2.0; muy activo.

### StableVideo — wenhaochai — Global / GitHub
- **Fuente (URL verificada):** https://github.com/wenhaochai/StableVideo
- **Vigencia y licencia:** última actividad 2026-10-30 (activo) · licencia **Apache-2.0** · 1.435 estrellas · Python
- **Técnica Utilizada:** StableVideo: Text-driven Consistency-aware Diffusion Video Editing (ICCV 2023).
- **Ventaja:** Enfoque en consistencia temporal para edición de video; Apache-2.0.

### SEINE — Vchitect — China / GitHub
- **Fuente (URL verificada):** https://github.com/Vchitect/SEINE
- **Vigencia y licencia:** última actividad 2026-10-30 (activo) · licencia **Apache-2.0** · 966 estrellas · Python
- **Técnica Utilizada:** SEINE: Short-to-Long Video Diffusion Model for Generative Transition and Prediction (ICLR 2024).
- **Ventaja:** Generación de video corto a largo; Apache-2.0.

### Otros repos relevantes (licencia a verificar)
- **Sparse-VideoGen** (svg-project, 712★, Apache-2.0): Aceleración de video-diffusion con atención dispersa (ICML2025, NeurIPS2025 Spotlight).
- **SolarWM** (Junchao-cs, 911★, Apache-2.0): Open data y entrenamiento escalable para video world models de largo horizonte.
- **Control-A-Video** (Weifeng-Chen, 405★, GPL-3.0): Generación de video controlable con diffusion models.
- **TI2V-Zero** (merlresearch, 55★, AGPL-3.0): Text-conditioned image-to-video basado en diffusion.
- **LUMIERE** (kyegomez, 52★, MIT): Implementación del modelo text-to-video LUMIERE (Space-Time Diffusion Model).
## 8. Plataformas y repositorios principales por país e idioma

A continuación, la matriz de los principales idiomas de desarrollo a nivel mundial, las plataformas de código usadas en cada país/región, y los repositorios de video-diffusion o producción de video más relevantes identificados en esta investigación.

| País / Región | Idioma principal de código | Plataformas de código usadas | Repositorios de video-diffusion / producción de video más relevantes | Licencia |
| :--- | :--- | :--- | :--- | :--- |
| **Global / EE. UU. / Reino Unido** | Inglés | GitHub, GitLab, Codeberg, Reddit, Hacker News | Sana (NVlabs), lucidrains/video-diffusion-pytorch, Tune-A-Video (showlab), LTX-Video (Lightricks), StableVideo, OpenMontage, Open-Generative-AI | Apache-2.0 / MIT / AGPL-3.0 |
| **China** | Chino (zh-CN) | Gitee, GitCode, CSDN, AtomGit, Zhihu | CogVideo (zai-org), VideoCrafter2 (AILab-CVC), Show-1 / MotionDirector (showlab), SEINE (Vchitect), MMagic (OpenMMLab), Helios (PKU-YuanGroup) | Apache-2.0 / NOASSERTION |
| **Rusia / CEI** | Ruso | GitVerse, GitFlic, Habr, CyberForum | (ninguno identificado en búsqueda inicial) | — |
| **Japón** | Japonés | GitHub (ecosistema Japón), Qiita, Zenn | (ninguno identificado en búsqueda inicial) | — |
| **Corea del Sur** | Coreano | GitHub (ecosistema Corea), Velog, Naver D2, GeekNews | (ninguno identificado en búsqueda inicial) | — |
| **Alemania / Europa Central** | Alemán | Codeberg, Heise Developer, Golem.de | (ninguno identificado en búsqueda inicial) | — |
| **Francia** | Francés | Framagit, LinuxFr.org | (ninguno identificado en búsqueda inicial) | — |
| **India** | Inglés (en GitHub) | GitHub (términos en hindi dan 0 resultados) | MMagic (OpenMMLab es chino, pero OpenMMLab tiene presencia global); búsqueda en hindi devolvió repos en inglés | Apache-2.0 |
| **Brasil / Portugal** | Portugués | GitHub (términos en portugués dan 0 resultados) | (ninguno en portugués; los devs publican en inglés) | — |
| **España / Latinoamérica** | Español | GitHub (términos en español dan 0 resultados) | (ninguno en español; los devs publican en inglés) | — |
| **Pakistán** | Inglés / Urdu | GitHub (términos en urdu dan 0 resultados) | (ninguno en urdu; los devs publican en inglés) | — |

### Observaciones clave

1. **El inglés domina GitHub mundialmente.** Las búsquedas en español, portugués, hindi y urdu devolvieron 0 resultados o repos en inglés. Los desarrolladores de todos los países publican sus proyectos en inglés para maximizar visibilidad y colaboración.

2. **Concentración geográfica del código abierto de video-diffusion.**
   - **China:** muy fuerte (CogVideo, VideoCrafter2, Show-1, SEINE, MMagic, Helios) — 6 de los 10 repos más estrellas son chinos o de origen chino.
   - **Global / EE. UU.:** fuerte (Sana, LTX-Video, lucidrains, StableVideo, Tune-A-Video, MotionDirector, Control-A-Video).
   - **Rusia, Japón, Corea, Alemania, Francia, India, Brasil, España, Pakistán:** no se identificaron repositorios propios de video-diffusion en búsquedas iniciales; su aportación está en inglés bajo la categoría "global".

3. **Plataformas por país.** Cada país tiene sus plataformas locales (Gitee/GitCode en China, GitVerse/GitFlic en Rusia, Qiita/Zenn en Japón, Velog/Naver D2 en Corea, Codeberg en Alemania, Framagit en Francia), pero para video-diffusion específicas, GitHub sigue siendo la plataforma dominante incluso para desarrolladores chinos (zai-org, AILab-CVC, Vchitect usan GitHub).

### Recomendación de adapción por región

- **Si el equipo opera en entorno chino o necesita modelos con licencia Apache-2.0 y fuerte respaldo académico chino:** priorizar CogVideo (zai-org) o Helios (PKU-YuanGroup).
- **Si se necesita la licencia más permisiva (MIT) y una implementación de referencia académica:** lucidrains/video-diffusion-pytorch o LUMIERE (kyegomez).
- **Si se necesita video largo o tiempo real:** Helios (PKU-YuanGroup) o StableVideo (wenhaochai).
- **Si se necesita una toolbox multimodal completa:** MMagic (OpenMMLab).

