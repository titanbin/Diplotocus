import json,sys,threading,webbrowser,re,ast,mimetypes,shutil,tempfile,uuid
import numpy as np
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import diplotocus.easings as easings
import diplotocus.animations as animations

SPECIAL_CLIP_TYPES = {
    "axis_zoom",
    "axis_limits",
    "axis_move",
    "axis_alpha",
    "fig_width_ratio",
    "fig_height_ratio",
}

def _safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default

def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)

def _normalize_scalar(value):
    if isinstance(value, np.ndarray):
        if value.size == 0:
            return None
        return _normalize_scalar(value.ravel()[0])
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return None
        return _normalize_scalar(value[0])
    if isinstance(value, np.generic):
        return value.item()
    return value

def _parse_scalar_like(value, default=None):
    if value is None:
        return default

    normalized = _normalize_scalar(value)
    if isinstance(normalized, str):
        text = normalized.strip()
        if text == "":
            return default

        if text.startswith("array(") and text.endswith(")"):
            text = text[6:-1].strip()

        try:
            parsed = ast.literal_eval(text)
        except Exception:
            return text
        return _normalize_scalar(parsed)

    return normalized

def _safe_name(name):
    text = str(name).strip().lower()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^a-z0-9_]+", "", text)
    return text

class GUI:
    """Serve the web GUI locally.

    Example:
        import diplotocus
        web_gui = diplotocus.GUI_web.GUI()
        web_gui.wait()  # Optional: block current process
    """

    def __init__(
        self,
        seq=None,
        plot_objects=None,
        min_tracks: int = 3,
        host: str = "localhost",
        port: int = 8008,
        open_browser: bool = True,
        auto_start: bool = True,
        block: bool | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._static_dir = Path(__file__).resolve().parent
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.url: str | None = None
        self.block = (not self._is_interactive()) if block is None else block
        self.seq = seq
        self.plot_objects = [] if plot_objects is None else plot_objects
        self.min_tracks = max(1, _safe_int(min_tracks, 3))

        self._lock = threading.RLock()
        self._anim_to_clip_id = {}
        self._clip_id_to_anim = {}
        self._clip_id_to_owner = {}
        self._clip_id_to_type = {}
        self._clip_rows = {}
        self._detached_clip_ids = set()
        self._clip_seed = 0
        self._render_revision = 0
        self._timeline_width_override = None
        self._row_count_override = None
        self._last_invalidated_from = 0
        self._temp_exports = {}

        if auto_start:
            self.serve(open_browser=open_browser)
            if self.block:
                self.wait()

    @staticmethod
    def _is_interactive() -> bool:
        return bool(getattr(sys, "ps1", False) or sys.flags.interactive)

    def _all_objects(self):
        objects = []
        for el in self.plot_objects:
            if not isinstance(el, dict):
                continue
            obj = el.get("object")
            if obj is None:
                continue
            objects.append(obj)
        return objects

    def _display_clip_type(self, type_key):
        return str(type_key or "clip").capitalize()

    def _clip_type_for_clip(self, clip_id, anim):
        mapped_type = self._clip_id_to_type.get(clip_id)
        if mapped_type:
            return mapped_type

        owner_index = self._find_clip_owner_index(clip_id)
        if owner_index is not None and 0 <= owner_index < len(self.plot_objects):
            entry = self.plot_objects[owner_index]
            if isinstance(entry, dict):
                owner_obj = entry.get("object")
                owner_type = _safe_name(owner_obj.__class__.__name__) if owner_obj is not None else ""
                if owner_type in SPECIAL_CLIP_TYPES:
                    return owner_type

        return _safe_name(anim.get("name", "")) or "clip"

    def _is_selectable_plot_entry(self, entry):
        return isinstance(entry, dict) and entry.get("object") is not None and not bool(entry.get("_gui_special", False))

    def _first_selectable_plot_object(self):
        for index, entry in enumerate(self.plot_objects):
            if self._is_selectable_plot_entry(entry):
                return index, entry.get("object")
        return None, None

    def _default_axis_for_special(self, source_object):
        source_axis = getattr(source_object, "axis", None)
        if source_axis is not None:
            return source_axis
        if self.seq is not None and hasattr(self.seq, "main_axis"):
            return self.seq.main_axis
        return None

    def _default_ratio_length(self, axis, use_width):
        if axis is None:
            return 2
        try:
            grid = axis.get_gridspec()
            if use_width:
                return max(1, int(getattr(grid, "ncols", 2)))
            return max(1, int(getattr(grid, "nrows", 2)))
        except Exception:
            return 2

    def _build_special_animation(self, clip_type, duration, delay, easing, axis):
        if clip_type == "axis_zoom":
            return animations.axis_zoom(zoom=1.0, duration=duration, delay=delay, easing=easing, axis=axis)

        if clip_type == "axis_limits":
            xlim = axis.get_xlim() if axis is not None else (0.0, 1.0)
            ylim = axis.get_ylim() if axis is not None else (0.0, 1.0)
            return animations.axis_limits(duration=duration, xlim=xlim, ylim=ylim, delay=delay, easing=easing, axis=axis)

        if clip_type == "axis_move":
            return animations.axis_move(end_pos=(0.0, 0.0), duration=duration, start_pos=None, delay=delay, easing=easing, axis=axis)

        if clip_type == "axis_alpha":
            return animations.axis_alpha(start_alpha=0.0, end_alpha=1.0, duration=duration, delay=delay, easing=easing, axis=axis)

        if clip_type == "fig_width_ratio":
            ncols = self._default_ratio_length(axis, use_width=True)
            ratios = tuple([1.0] * ncols)
            return animations.fig_width_ratio(start_widths=ratios, end_widths=ratios, duration=duration, delay=delay, easing=easing, axis=axis)

        if clip_type == "fig_height_ratio":
            nrows = self._default_ratio_length(axis, use_width=False)
            ratios = tuple([1.0] * nrows)
            return animations.fig_height_ratio(start_heights=ratios, end_heights=ratios, duration=duration, delay=delay, easing=easing, axis=axis)

        raise ValueError(f"Unsupported special clip type: {clip_type}")

    def _next_clip_id(self):
        self._clip_seed += 1
        return f"clip-{self._clip_seed}"

    def _clip_id_for_anim(self, anim):
        key = id(anim)
        if key not in self._anim_to_clip_id:
            clip_id = self._next_clip_id()
            self._anim_to_clip_id[key] = clip_id
            self._clip_id_to_anim[clip_id] = anim
        return self._anim_to_clip_id[key]

    def _type_from_anim(self, clip_id, anim):
        return self._display_clip_type(self._clip_type_for_clip(clip_id, anim))

    def _max_frame(self):
        max_frame = self._rightmost_clip()
        if self._timeline_width_override is not None:
            return max(50, max(max_frame, int(self._timeline_width_override)))
        if max_frame == 0:
            return 150
        return max(50, max_frame)

    def _rightmost_clip(self):
        rightmost = 0
        for obj in self._all_objects():
            for anim in getattr(obj, "anims", []):
                rightmost = max(rightmost, _safe_int(anim.get("delay", 0)) + _safe_int(anim.get("duration", 0)))
        return rightmost

    def _serialize_clips(self):
        clips = []
        for clip_id, anim in self._clip_id_to_anim.items():
            anim = self._clip_id_to_anim.get(clip_id)
            if anim is None:
                raise KeyError(f"Unknown clip id: {clip_id}")
            clip_type = self._clip_type_for_clip(clip_id, anim)
            
            object_options = ["None"]
            for obj in self.plot_objects:
                if not self._is_selectable_plot_entry(obj):
                    continue
                if clip_type == "morph" and not ("new_x" in obj and "new_y" in obj):
                    continue
                object_options.append(obj["name"])
            
            if clip_type in SPECIAL_CLIP_TYPES:
                current_object_id = 0
            elif clip_id in self._clip_id_to_owner:
                owner_index = self._clip_id_to_owner.get(clip_id)
                current_object_id = 0 if owner_index is None else owner_index + 1
            else:
                owner_index = self._find_clip_owner_index(clip_id)
                current_object_id = 0 if owner_index is None else owner_index + 1

            clip = {
                "id": clip_id,
                "type": self._type_from_anim(clip_id, anim),
                "x": _safe_int(anim.get("delay", 0)),
                "width": max(1, _safe_int(anim.get("duration", 1))),
                "row": self._clip_rows.get(clip_id, 0),
                "plotObjectName":object_options[current_object_id]
            }
            clips.append(clip)

            if clip_id in self._detached_clip_ids:
                self._clip_id_to_owner[clip_id] = None
                continue

            if clip_id not in self._clip_id_to_owner:
                owner_index = self._find_clip_owner_index(clip_id)
                if owner_index is not None:
                    self._clip_id_to_owner[clip_id] = owner_index

        row_end = []
        clips.sort(key=lambda c: (c["x"], c["width"]))
        for clip in clips:
            if clip["id"] in self._clip_rows:
                continue
            placed = False
            for row_i, end_x in enumerate(row_end):
                if clip["x"] >= end_x:
                    clip["row"] = row_i
                    row_end[row_i] = clip["x"] + clip["width"]
                    placed = True
                    break
            if not placed:
                clip["row"] = len(row_end)
                row_end.append(clip["x"] + clip["width"])
            self._clip_rows[clip["id"]] = clip["row"]

        return clips

    def _state_payload(self):
        clips = self._serialize_clips()
        row_count = max(self.min_tracks, 1 + max((clip["row"] for clip in clips), default=0))
        if self._row_count_override is not None:
            row_count = max(row_count, int(self._row_count_override))
        return {
            "trackWidth": self._max_frame(),
            "rowCount": row_count,
            "minRowCount": self.min_tracks,
            "clips": clips,
            "hasSequence": self.seq is not None,
            "hasPlotObjects": len(self._all_objects()) > 0,
            "renderRevision": self._render_revision,
            "sequenceName": getattr(self.seq, "name", None),
            "invalidatedFromFrame": self._last_invalidated_from,
        }

    def _render_dirs(self):
        if self.seq is None:
            return []
        dirs = [Path(self.seq.name)]
        if hasattr(self.seq, "full_path"):
            dirs.insert(0, Path(self.seq.full_path) / self.seq.name)
        unique = []
        seen = set()
        for d in dirs:
            key = str(d.resolve()) if d.exists() else str(d)
            if key in seen:
                continue
            seen.add(key)
            unique.append(d)
        return unique

    def _invalidate_render_cache(self, from_frame=None):
        if self.seq is None:
            return
        if from_frame is None:
            from_frame = 0
        self._last_invalidated_from = max(0, int(from_frame))
        prefix = f"{self.seq.name}_"
        pattern = re.compile(rf"^{re.escape(self.seq.name)}_(\d+)\.png$")
        for d in self._render_dirs():
            if not d.exists() or not d.is_dir():
                continue
            for png in d.glob(f"{prefix}*.png"):
                m = pattern.match(png.name)
                if not m:
                    continue
                frame_n = int(m.group(1))
                if frame_n < int(from_frame):
                    continue
                try:
                    png.unlink()
                except OSError:
                    pass
        self._render_revision += 1

    def _clear_render_cache_on_load(self):
        if self.seq is None:
            return
        prefix = f"{self.seq.name}_"
        for d in self._render_dirs():
            if not d.exists() or not d.is_dir():
                continue
            for f in d.glob(f"{prefix}*.png"):
                try:
                    f.unlink()
                except OSError:
                    pass
        self._last_invalidated_from = 0
        self._render_revision += 1

    def _create_clip(self, clip_type, x, width, row):
        obj_index, target = self._first_selectable_plot_object()
        if target is None:
            raise RuntimeError("No plot objects available. Pass plot_objects to GUI_web.GUI(...).")

        name = _safe_name(clip_type)
        duration = max(1, _safe_int(width, 120))
        delay = max(0, _safe_int(x, 0))

        if name in SPECIAL_CLIP_TYPES:
            easing = easings.easeLinear()
            axis = self._default_axis_for_special(target)
            special_object = self._build_special_animation(name, duration, delay, easing, axis)
            self.plot_objects.append({
                "name": str(clip_type),
                "object": special_object,
                "_gui_special": True,
            })

            anim = special_object.anims[0]
            clip_id = self._clip_id_for_anim(anim)
            self._clip_id_to_owner[clip_id] = len(self.plot_objects) - 1
            self._clip_id_to_type[clip_id] = name
            self._clip_rows[clip_id] = max(0, _safe_int(row, 0))
            self._invalidate_render_cache(from_frame=delay)
            return clip_id

        before = len(target.anims)
        if name == "translate":
            target.translate((0, 0), (1, 1), duration=duration, delay=delay)
        elif name == "rotate":
            target.rotate(0, 360, duration=duration, delay=delay)
        elif name == "scale":
            target.scale((1, 1), (2, 2), duration=duration, delay=delay)
        elif name == "tween":
            target.tween(property="alpha", start=0, end=1, duration=duration, delay=delay)
        elif name == "draw":
            target.draw(duration=duration, delay=delay)
        elif name == "morph":
            if isinstance(self.plot_objects[obj_index], dict) and "new_x" in self.plot_objects[obj_index] and "new_y" in self.plot_objects[obj_index]:
                target.morph(
                    new_x=self.plot_objects[obj_index]["new_x"],
                    new_y=self.plot_objects[obj_index]["new_y"],
                    duration=duration,
                    delay=delay,
                )
            else:
                target.translate((0, 0), (1, 1), duration=duration, delay=delay)
        elif name == "sequence":
            target.sequence(duration=duration, delay=delay)
        else:
            target.translate((0, 0), (1, 1), duration=duration, delay=delay)

        if len(target.anims) <= before:
            raise RuntimeError("Could not create animation clip.")

        anim = target.anims[-1]
        clip_id = self._clip_id_for_anim(anim)
        self._clip_id_to_owner[clip_id] = obj_index
        self._clip_id_to_type[clip_id] = name
        self._clip_rows[clip_id] = max(0, _safe_int(row, 0))
        self._invalidate_render_cache(from_frame=delay)
        return clip_id

    def _update_clip(self, clip_id, x, width, row):
        anim = self._clip_id_to_anim.get(clip_id)
        if anim is None:
            raise KeyError(f"Unknown clip id: {clip_id}")
        old_delay = _safe_int(anim.get("delay", 0))
        anim["delay"] = max(0, _safe_int(x, anim.get("delay", 0)))
        anim["duration"] = max(1, _safe_int(width, anim.get("duration", 1)))
        if row is not None:
            self._clip_rows[clip_id] = max(0, _safe_int(row, 0))
        self._invalidate_render_cache(from_frame=min(old_delay, anim["delay"]))

    def _available_easings(self):
        names = []
        for name in dir(easings):
            if name.startswith("ease"):
                candidate = getattr(easings, name)
                if callable(candidate):
                    names.append(name)
        return sorted(set(names))

    def _find_clip_owner_index(self, clip_id):
        owner_index = self._clip_id_to_owner.get(clip_id)
        if owner_index is not None and 0 <= owner_index < len(self.plot_objects):
            return owner_index

        anim = self._clip_id_to_anim.get(clip_id)
        if anim is None:
            return None

        for index, entry in enumerate(self.plot_objects):
            if not isinstance(entry, dict):
                continue
            owner_obj = entry.get("object")
            if owner_obj is None:
                continue
            if anim in getattr(owner_obj, "anims", []):
                return index
        return None

    def _clip_properties(self, clip_id):
        anim = self._clip_id_to_anim.get(clip_id)
        if anim is None:
            raise KeyError(f"Unknown clip id: {clip_id}")

        easing_obj = anim.get("easing")
        easing_name = easing_obj.__class__.__name__ if easing_obj is not None else "easeLinear"
        props = {
            "id": clip_id,
            "type": self._type_from_anim(clip_id, anim),
            "delay": _safe_int(anim.get("delay", 0)),
            "duration": max(1, _safe_int(anim.get("duration", 1))),
            "persistent": bool(anim.get("persistent", True)),
            "easing": easing_name,
            "availableEasings": self._available_easings(),
        }

        clip_type = self._clip_type_for_clip(clip_id, anim)
        object_options = [{"id": 0, "name": "None"}]
        for i, obj in enumerate(self.plot_objects):
            if not self._is_selectable_plot_entry(obj):
                continue
            if clip_type == "morph" and not ("new_x" in obj and "new_y" in obj):
                continue
            object_options.append({"id": i + 1, "name": obj["name"]})

        if clip_type in SPECIAL_CLIP_TYPES:
            current_object_id = 0
        elif clip_id in self._clip_id_to_owner:
            owner_index = self._clip_id_to_owner.get(clip_id)
            current_object_id = 0 if owner_index is None else owner_index + 1
        else:
            owner_index = self._find_clip_owner_index(clip_id)
            current_object_id = 0 if owner_index is None else owner_index + 1

        props["plotObjectOptions"] = object_options
        props["plotObjectId"] = current_object_id

        name = clip_type
        if name in {"translate", "scale", "axis_move"}:
            start = anim.get("start", (0, 0))
            end = anim.get("end", (1, 1))
            props.update({
                "start_x": float(start[0]),
                "start_y": float(start[1]),
                "end_x": float(end[0]),
                "end_y": float(end[1]),
            })
        elif name == "axis_zoom":
            props.update({"zoom": float(anim.get("zoom", 1.0))})
        elif name == "axis_limits":
            xlim = anim.get("xlim")
            ylim = anim.get("ylim")
            props.update({
                "xlim_left": None if xlim is None else float(xlim[0]),
                "xlim_right": None if xlim is None else float(xlim[1]),
                "ylim_bottom": None if ylim is None else float(ylim[0]),
                "ylim_top": None if ylim is None else float(ylim[1]),
            })
        elif name == "rotate":
            props.update({
                "start": float(anim.get("start", 0)),
                "end": float(anim.get("end", 360)),
            })
        elif name == "axis_alpha":
            props.update({
                "start": float(anim.get("start", 1.0)),
                "end": float(anim.get("end", 1.0)),
            })
        elif name == "tween":
            tween_property = _normalize_scalar(anim.get("property", "alpha"))
            tween_start = _normalize_scalar(anim.get("start", 0))
            tween_end = _normalize_scalar(anim.get("end", 1))
            props.update({
                "tween_property": "alpha" if tween_property is None else str(tween_property),
                "tween_start": "0" if tween_start is None else str(tween_start),
                "tween_end": "1" if tween_end is None else str(tween_end),
            })
        elif name == "draw":
            props.update({
                "reverse": str([anim.get("reverse",False)])
            })
        elif name in {"fig_width_ratio", "fig_height_ratio"}:
            props.update({
                "ratio_start": str(list(np.ravel(anim.get("start", [1.0])))),
                "ratio_end": str(list(np.ravel(anim.get("end", [1.0])))),
            })

        props["typeKey"] = clip_type

        return props

    def _parse_list_like(self, value, default):
        if value is None:
            return default
        if isinstance(value, (list, tuple)):
            return list(value)
        if isinstance(value, str):
            try:
                parsed = ast.literal_eval(value)
            except Exception:
                return default
            if isinstance(parsed, (list, tuple)):
                return list(parsed)
            return default
        return default

    def _update_clip_properties(self, clip_id, payload):
        anim = self._clip_id_to_anim.get(clip_id)
        if anim is None:
            raise KeyError(f"Unknown clip id: {clip_id}")

        clip_type = self._clip_type_for_clip(clip_id, anim)

        if clip_type not in SPECIAL_CLIP_TYPES:
            old_owner_index = self._find_clip_owner_index(clip_id)
            new_object_id = _safe_int(payload.get("plotObjectId", old_owner_index + 1 if old_owner_index is not None else 0), 0)
            if new_object_id == 0:
                if old_owner_index is not None and 0 <= old_owner_index < len(self.plot_objects):
                    old_owner_entry = self.plot_objects[old_owner_index]
                    old_owner_obj = old_owner_entry.get("object") if isinstance(old_owner_entry, dict) else None
                    if old_owner_obj is not None and anim in old_owner_obj.anims:
                        old_owner_obj.anims.remove(anim)
                self._detached_clip_ids.add(clip_id)
                self._clip_id_to_owner[clip_id] = None
            else:
                new_owner_index = new_object_id - 1
                if not (0 <= new_owner_index < len(self.plot_objects)):
                    raise ValueError("Invalid plot object selection.")

                if old_owner_index is not None and old_owner_index != new_owner_index:
                    old_owner_entry = self.plot_objects[old_owner_index]
                    old_owner_obj = old_owner_entry.get("object") if isinstance(old_owner_entry, dict) else None
                    if old_owner_obj is not None and anim in old_owner_obj.anims:
                        old_owner_obj.anims.remove(anim)

                new_owner_entry = self.plot_objects[new_owner_index]
                if not isinstance(new_owner_entry, dict) or "object" not in new_owner_entry:
                    raise ValueError("Invalid plot object selection.")

                new_owner_obj = new_owner_entry["object"]
                if anim not in new_owner_obj.anims:
                    new_owner_obj.anims.append(anim)
                self._detached_clip_ids.discard(clip_id)
                self._clip_id_to_owner[clip_id] = new_owner_index

        old_delay = _safe_int(anim.get("delay", 0))

        anim["delay"] = max(0, _safe_int(payload.get("delay", anim.get("delay", 0))))
        anim["duration"] = max(1, _safe_int(payload.get("duration", anim.get("duration", 1))))
        anim["persistent"] = bool(payload.get("persistent", anim.get("persistent", True)))

        easing_name = payload.get("easing")
        if easing_name and hasattr(easings, easing_name):
            anim["easing"] = getattr(easings, easing_name)()

        name = clip_type
        if name in {"translate", "scale", "axis_move"}:
            start_x = float(payload.get("start_x", anim.get("start", (0, 0))[0]))
            start_y = float(payload.get("start_y", anim.get("start", (0, 0))[1]))
            end_x = float(payload.get("end_x", anim.get("end", (1, 1))[0]))
            end_y = float(payload.get("end_y", anim.get("end", (1, 1))[1]))
            anim["start"] = (start_x, start_y)
            anim["end"] = (end_x, end_y)
        elif name == "axis_zoom":
            anim["zoom"] = _safe_float(payload.get("zoom", anim.get("zoom", 1.0)), 1.0)
        elif name == "axis_limits":
            current_xlim = anim.get("xlim")
            current_ylim = anim.get("ylim")
            anim["xlim"] = (
                _safe_float(payload.get("xlim_left", current_xlim[0] if current_xlim is not None else 0.0), 0.0),
                _safe_float(payload.get("xlim_right", current_xlim[1] if current_xlim is not None else 1.0), 1.0),
            )
            anim["ylim"] = (
                _safe_float(payload.get("ylim_bottom", current_ylim[0] if current_ylim is not None else 0.0), 0.0),
                _safe_float(payload.get("ylim_top", current_ylim[1] if current_ylim is not None else 1.0), 1.0),
            )
        elif name == "rotate":
            anim["start"] = float(payload.get("start", anim.get("start", 0)))
            anim["end"] = float(payload.get("end", anim.get("end", 360)))
        elif name == "axis_alpha":
            anim["start"] = _safe_float(payload.get("start", anim.get("start", 1.0)), 1.0)
            anim["end"] = _safe_float(payload.get("end", anim.get("end", 1.0)), 1.0)
        elif name in {"fig_width_ratio", "fig_height_ratio"}:
            starts = self._parse_list_like(payload.get("ratio_start"), list(np.ravel(anim.get("start", [1.0]))))
            ends = self._parse_list_like(payload.get("ratio_end"), list(np.ravel(anim.get("end", [1.0]))))
            if len(starts) == 0:
                starts = [1.0]
            if len(ends) == 0:
                ends = [1.0]
            n = min(len(starts), len(ends))
            if n == 0:
                n = 1
                starts = [1.0]
                ends = [1.0]
            starts = np.ravel(starts[:n]).astype(float)
            ends = np.ravel(ends[:n]).astype(float)
            start_sum = np.sum(starts)
            end_sum = np.sum(ends)
            starts = starts / start_sum if start_sum != 0 else np.ones_like(starts) / len(starts)
            ends = ends / end_sum if end_sum != 0 else np.ones_like(ends) / len(ends)
            anim["start"] = starts
            anim["end"] = ends
        elif name == "tween":
            owner_index = self._clip_id_to_owner.get(clip_id)
            owner_obj = None
            if owner_index is not None and 0 <= owner_index < len(self.plot_objects):
                entry = self.plot_objects[owner_index]
                if isinstance(entry, dict):
                    owner_obj = entry.get("object")

            prop = _parse_scalar_like(payload.get("tween_property"), anim.get("property", "alpha"))
            start = _parse_scalar_like(payload.get("tween_start"), anim.get("start", 0))
            end = _parse_scalar_like(payload.get("tween_end"), anim.get("end", 1))

            if prop is None or str(prop).strip() == "":
                prop = "alpha"

            props = [str(prop)]
            starts = [start]
            ends = [end]

            if owner_obj is not None:
                props = list(owner_obj.get_main_alias(props))
                props, starts, ends = owner_obj.sanitize_colors(props, starts, ends)

            anim["property"] = props[0]
            anim["start"] = starts[0]
            anim["end"] = ends[0]
        elif name == "draw":
            reverse_val = payload.get('reverse', False)
            if isinstance(reverse_val, str):
                anim['reverse'] = reverse_val.lower() in ['true', '1', 'yes']
            else:
                anim['reverse'] = bool(reverse_val)

        self._invalidate_render_cache(from_frame=min(old_delay, anim["delay"]))

    def _set_timeline_width(self, width):
        width = max(50, _safe_int(width, 1000))
        width = max(width, self._rightmost_clip())
        self._timeline_width_override = width

    def _set_row_count(self, row_count):
        self._row_count_override = max(self.min_tracks, _safe_int(row_count, self.min_tracks))

    def _delete_track_row(self, row):
        target_row = max(0, _safe_int(row, 0))
        current_rows = self._state_payload()["rowCount"]
        if target_row < self.min_tracks:
            raise ValueError(f"Cannot delete protected track. First {self.min_tracks} tracks are required.")
        if current_rows <= self.min_tracks:
            raise ValueError(f"Cannot delete track: minimum row count is {self.min_tracks}.")
        if target_row >= current_rows:
            raise ValueError("Invalid track row index.")

        removed_clip_ids = [clip_id for clip_id, clip_row in self._clip_rows.items() if clip_row == target_row]
        invalidate_from = None

        for clip_id in removed_clip_ids:
            anim = self._clip_id_to_anim.get(clip_id)
            if anim is not None:
                delay = _safe_int(anim.get("delay", 0), 0)
                invalidate_from = delay if invalidate_from is None else min(invalidate_from, delay)

            owner_index = self._find_clip_owner_index(clip_id)
            if owner_index is not None and 0 <= owner_index < len(self.plot_objects):
                owner_entry = self.plot_objects[owner_index]
                owner_obj = owner_entry.get("object") if isinstance(owner_entry, dict) else None
                if owner_obj is not None and anim is not None and anim in owner_obj.anims:
                    owner_obj.anims.remove(anim)

            if anim is not None:
                key = id(anim)
                if self._anim_to_clip_id.get(key) == clip_id:
                    self._anim_to_clip_id.pop(key, None)

            self._clip_rows.pop(clip_id, None)
            self._clip_id_to_anim.pop(clip_id, None)
            self._clip_id_to_owner.pop(clip_id, None)
            self._clip_id_to_type.pop(clip_id, None)
            self._detached_clip_ids.discard(clip_id)

            if owner_index is not None and 0 <= owner_index < len(self.plot_objects):
                owner_entry = self.plot_objects[owner_index]
                if isinstance(owner_entry, dict) and owner_entry.get("_gui_special", False):
                    owner_entry["object"] = None

        for clip_id in list(self._clip_rows.keys()):
            if self._clip_rows[clip_id] > target_row:
                self._clip_rows[clip_id] -= 1

        self._row_count_override = max(self.min_tracks, current_rows - 1)

        if invalidate_from is not None:
            self._invalidate_render_cache(from_frame=invalidate_from)

    def _delete_clips(self, clip_ids):
        if not isinstance(clip_ids, list):
            clip_ids = [clip_ids]

        removed_any = False
        invalidate_from = None

        for clip_id in clip_ids:
            clip_id = str(clip_id)
            anim = self._clip_id_to_anim.get(clip_id)
            if anim is None:
                continue

            removed_any = True
            delay = _safe_int(anim.get("delay", 0), 0)
            invalidate_from = delay if invalidate_from is None else min(invalidate_from, delay)

            owner_index = self._find_clip_owner_index(clip_id)
            if owner_index is not None and 0 <= owner_index < len(self.plot_objects):
                owner_entry = self.plot_objects[owner_index]
                owner_obj = owner_entry.get("object") if isinstance(owner_entry, dict) else None
                if owner_obj is not None and anim in owner_obj.anims:
                    owner_obj.anims.remove(anim)

            key = id(anim)
            if self._anim_to_clip_id.get(key) == clip_id:
                self._anim_to_clip_id.pop(key, None)

            self._clip_rows.pop(clip_id, None)
            self._clip_id_to_anim.pop(clip_id, None)
            self._clip_id_to_owner.pop(clip_id, None)
            self._clip_id_to_type.pop(clip_id, None)
            self._detached_clip_ids.discard(clip_id)

            if owner_index is not None and 0 <= owner_index < len(self.plot_objects):
                owner_entry = self.plot_objects[owner_index]
                if isinstance(owner_entry, dict) and owner_entry.get("_gui_special", False):
                    owner_entry["object"] = None

        if not removed_any:
            raise KeyError("No valid clip ids provided.")

        if invalidate_from is not None:
            self._invalidate_render_cache(from_frame=invalidate_from)

    def _frame_file_paths(self, frame):
        filename = f"{self.seq.name}_{frame}.png"
        paths = [Path(self.seq.name) / filename]
        if hasattr(self.seq, "full_path"):
            paths.insert(0, Path(self.seq.full_path) / self.seq.name / filename)
        return paths

    def _frame_url_path(self, frame):
        if self.seq is None:
            raise RuntimeError("No Sequence object available.")
        frame = max(0, _safe_int(frame, 0))
        return f"/frames/{self.seq.name}_{frame}.png"

    def _frame_path_from_name(self, filename):
        if self.seq is None:
            return None
        expected_prefix = f"{self.seq.name}_"
        if not filename.startswith(expected_prefix) or not filename.endswith(".png"):
            return None

        for d in self._render_dirs():
            p = d / filename
            if p.is_file():
                return p
        return None

    def _ensure_frame_rendered(self, frame):
        frame = max(0, _safe_int(frame, 0))

        for path in self._frame_file_paths(frame):
            if path.is_file():
                return path

        if self.seq is None:
            raise RuntimeError("No Sequence object available. Pass seq to GUI_web.GUI(seq=...).")

        objs = self._all_objects()
        if len(objs) == 0:
            raise RuntimeError("No plot objects available. Pass plot_objects to GUI_web.GUI(...).")

        self.seq.clean_all()
        self.seq.plot(objs, x=frame)

        for path in self._frame_file_paths(frame):
            if path.is_file():
                return path

        raise RuntimeError("Rendered frame file not found after sequence.plot call.")

    def _render_frame_png(self, frame):
        return self._ensure_frame_rendered(frame).read_bytes()

    def _export_video_to_temp(self, timeline_width=None):
        if self.seq is None:
            raise RuntimeError("No Sequence object available. Pass seq to GUI_web.GUI(seq=...).")

        max_frame = _safe_int(timeline_width, self._max_frame())
        self.seq.x = max(self.seq.x, max_frame + 1)

        ext = ".mov" if getattr(self.seq, "transparent", False) else ".mp4"
        tmpdir = Path(tempfile.mkdtemp(prefix="diplotocus_export_"))
        outfile = tmpdir / f"{getattr(self.seq, 'name', 'video')}{ext}"

        self.seq.save_video(path=str(outfile), clean=False)
        token = uuid.uuid4().hex
        self._temp_exports[token] = {"path": outfile, "dir": tmpdir}
        ctype = mimetypes.guess_type(str(outfile))[0] or "application/octet-stream"
        return {
            "token": token,
            "filename": outfile.name,
            "contentType": ctype,
        }

    def _read_and_cleanup_temp_export(self, token):
        entry = self._temp_exports.pop(token, None)
        if entry is None:
            return None
        path = entry["path"]
        tmpdir = entry["dir"]
        if not path.is_file():
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except OSError:
                pass
            return None
        data = path.read_bytes()
        filename = path.name
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except OSError:
            pass
        return data, filename, ctype

    def _save_project_file(self, filename):
        if self.seq is None or not hasattr(self.seq, "save_project"):
            raise RuntimeError("Save project unavailable: no sequence attached.")

        name = str(filename or "").strip()
        if not name:
            raise ValueError("Missing filename.")

        target = Path(name).expanduser()
        if not target.is_absolute():
            target = Path.cwd() / target
        target.parent.mkdir(parents=True, exist_ok=True)

        self.seq.save_project(str(target))
        return str(target)

    def _read_project_file(self, filename):
        path = Path(str(filename or "").strip()).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.is_file():
            raise FileNotFoundError("Project file not found.")
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        return data, path.name, ctype

    def _make_handler(self):
        gui = self
        static_dir = str(self._static_dir)

        class Handler(BaseHTTPRequestHandler):
            def _is_client_disconnect(self, exc):
                if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
                    return True
                if isinstance(exc, OSError) and getattr(exc, "errno", None) in {32, 54, 104}:
                    return True
                return False

            def _send_json(self, payload, status=200):
                body = json.dumps(payload).encode("utf-8")
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as exc:
                    if not self._is_client_disconnect(exc):
                        raise

            def _send_bytes(self, payload, content_type="application/octet-stream", status=200):
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except Exception as exc:
                    if not self._is_client_disconnect(exc):
                        raise

            def _send_error(self, message, status=400):
                self._send_json({"error": message}, status=status)

            def _read_json(self):
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    return json.loads(raw.decode("utf-8") or "{}")
                except Exception:
                    return {}

            def _serve_static(self, rel_path):
                rel = rel_path.lstrip("/")
                if rel == "":
                    rel = "GUI.html"
                path = (Path(static_dir) / rel).resolve()
                base = Path(static_dir).resolve()
                if not str(path).startswith(str(base)) or not path.is_file():
                    self.send_error(404)
                    return

                if path.suffix == ".html":
                    ctype = "text/html; charset=utf-8"
                elif path.suffix == ".css":
                    ctype = "text/css; charset=utf-8"
                elif path.suffix == ".js":
                    ctype = "application/javascript; charset=utf-8"
                else:
                    ctype = "application/octet-stream"

                data = path.read_bytes()
                self._send_bytes(data, ctype)

            def do_GET(self):
                parsed = urlparse(self.path)

                if parsed.path == "/api/state":
                    with gui._lock:
                        gui._clear_render_cache_on_load()
                        payload = gui._state_payload()
                    self._send_json(payload)
                    return

                if parsed.path == "/api/save-video-file":
                    params = parse_qs(parsed.query)
                    token = str(params.get("token", [""])[0])
                    if not token:
                        self._send_error("Missing token.", status=400)
                        return
                    with gui._lock:
                        payload = gui._read_and_cleanup_temp_export(token)
                    if payload is None:
                        self._send_error("Export file not found.", status=404)
                        return
                    data, filename, ctype = payload
                    try:
                        self.send_response(200)
                        self.send_header("Content-Type", ctype)
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                        self.end_headers()
                        self.wfile.write(data)
                    except Exception as exc:
                        if not self._is_client_disconnect(exc):
                            raise
                    return

                if parsed.path == "/api/save-project-file":
                    params = parse_qs(parsed.query)
                    filename = str(params.get("filename", [""])[0])
                    if not filename:
                        self._send_error("Missing filename.", status=400)
                        return
                    try:
                        with gui._lock:
                            data, download_name, ctype = gui._read_project_file(filename)
                        self.send_response(200)
                        self.send_header("Content-Type", ctype)
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
                        self.end_headers()
                        self.wfile.write(data)
                    except Exception as exc:
                        self._send_error(str(exc), status=404 if isinstance(exc, FileNotFoundError) else 400)
                    return

                if parsed.path == "/api/render-frame":
                    params = parse_qs(parsed.query)
                    frame = _safe_int(params.get("frame", [0])[0], 0)
                    try:
                        with gui._lock:
                            data = gui._render_frame_png(frame)
                        self._send_bytes(data, "image/png")
                    except Exception as exc:
                        self._send_error(str(exc), status=500)
                    return

                if parsed.path.startswith("/frames/"):
                    filename = parsed.path.split("/frames/", 1)[-1]
                    with gui._lock:
                        frame_path = gui._frame_path_from_name(filename)
                    if frame_path is None:
                        self._send_error("Frame not found.", status=404)
                        return
                    try:
                        self._send_bytes(frame_path.read_bytes(), "image/png")
                    except Exception as exc:
                        self._send_error(str(exc), status=500)
                    return

                self._serve_static(parsed.path)

            def do_POST(self):
                parsed = urlparse(self.path)
                payload = self._read_json()

                if parsed.path == "/api/clip/create":
                    try:
                        with gui._lock:
                            clip_id = gui._create_clip(
                                payload.get("type", "Translate"),
                                payload.get("x", 0),
                                payload.get("width", 120),
                                payload.get("row", 0),
                            )
                            state = gui._state_payload()
                        self._send_json({"ok": True, "clipId": clip_id, "state": state})
                    except Exception as exc:
                        self._send_error(str(exc), status=400)
                    return

                if parsed.path == "/api/clip/update":
                    try:
                        with gui._lock:
                            gui._update_clip(
                                payload.get("id", ""),
                                payload.get("x", 0),
                                payload.get("width", 120),
                                payload.get("row"),
                            )
                            state = gui._state_payload()
                        self._send_json({"ok": True, "state": state})
                    except Exception as exc:
                        self._send_error(str(exc), status=400)
                    return

                if parsed.path == "/api/clip/delete":
                    try:
                        with gui._lock:
                            if "ids" in payload:
                                gui._delete_clips(payload.get("ids", []))
                            else:
                                gui._delete_clips(payload.get("id", ""))
                            state = gui._state_payload()
                        self._send_json({"ok": True, "state": state})
                    except Exception as exc:
                        self._send_error(str(exc), status=400)
                    return

                if parsed.path == "/api/clip/get":
                    try:
                        with gui._lock:
                            props = gui._clip_properties(payload.get("id", ""))
                        self._send_json({"ok": True, "properties": props})
                    except Exception as exc:
                        self._send_error(str(exc), status=400)
                    return

                if parsed.path == "/api/clip/properties":
                    try:
                        with gui._lock:
                            gui._update_clip_properties(payload.get("id", ""), payload)
                            state = gui._state_payload()
                        self._send_json({"ok": True, "state": state})
                    except Exception as exc:
                        self._send_error(str(exc), status=400)
                    return

                if parsed.path == "/api/timeline/width":
                    try:
                        with gui._lock:
                            gui._set_timeline_width(payload.get("width", 1000))
                            if "rowCount" in payload:
                                gui._set_row_count(payload.get("rowCount", gui.min_tracks))
                            state = gui._state_payload()
                        self._send_json({"ok": True, "state": state})
                    except Exception as exc:
                        self._send_error(str(exc), status=400)
                    return

                if parsed.path == "/api/timeline/rows":
                    try:
                        with gui._lock:
                            gui._set_row_count(payload.get("rowCount", gui.min_tracks))
                            state = gui._state_payload()
                        self._send_json({"ok": True, "state": state})
                    except Exception as exc:
                        self._send_error(str(exc), status=400)
                    return

                if parsed.path == "/api/timeline/delete-row":
                    try:
                        with gui._lock:
                            gui._delete_track_row(payload.get("row", 0))
                            state = gui._state_payload()
                        self._send_json({"ok": True, "state": state})
                    except Exception as exc:
                        self._send_error(str(exc), status=400)
                    return

                if parsed.path == "/api/render":
                    try:
                        frame = _safe_int(payload.get("frame", 0), 0)
                        with gui._lock:
                            gui._ensure_frame_rendered(frame)
                            frame_path = gui._frame_url_path(frame)
                            rev = gui._render_revision
                        self._send_json({"ok": True, "framePath": frame_path, "renderRevision": rev, "frame": frame})
                    except Exception as exc:
                        self._send_error(str(exc), status=400)
                    return

                if parsed.path == "/api/save-video-temp":
                    try:
                        with gui._lock:
                            export = gui._export_video_to_temp(
                                timeline_width=payload.get("timelineWidth"),
                            )
                        self._send_json({"ok": True, **export})
                    except Exception as exc:
                        self._send_error(str(exc), status=400)
                    return

                if parsed.path == "/api/save-project":
                    try:
                        with gui._lock:
                            filename = gui._save_project_file(payload.get("filename", ""))
                        self._send_json({"ok": True, "filename": filename})
                    except Exception as exc:
                        self._send_error(str(exc), status=400)
                    return

                self._send_error("Unknown API endpoint.", status=404)

            def log_message(self, format, *args):
                return

        return Handler

    def serve(self, open_browser: bool = True) -> str:
        if self._server is not None:
            if self.url is not None:
                return self.url
            raise RuntimeError("Server is already running.")

        try:
            self._server = ThreadingHTTPServer((self.host, self.port), self._make_handler())
        except OSError as exc:
            raise RuntimeError(
                f"Could not start web GUI server on {self.host}:{self.port}. "
                "Try another port."
            ) from exc

        self.url = f"http://{self.host}:{self.port}/GUI.html"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        print(f"Diplotocus web GUI running at {self.url}")
        print("Use Ctrl+C in the terminal or call .stop() to stop the server.")

        if open_browser:
            webbrowser.open(self.url)

        return self.url

    def wait(self) -> None:
        if self._thread is None:
            return
        try:
            while self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=0.2)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None
