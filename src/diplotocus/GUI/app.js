/* global $ */
(function () {
  const state = {
    rowCount: 3,
    minRowCount: 3,
    trackWidth: 1000,
    trackHeight: 52,
    clipSeed: 0,
    clips: [],
    pinX: 0,
    renderedFrames: new Set(),
    pinDragging: false,
    previewUrl: null,
    hasSequence: false,
    hasPlotObjects: false,
    loadingState: false,
    isPlaying: false,
    loopEnabled: false,
    saveVideoPending: false,
    saveVideoInProgress: false,
    saveVideoFileName: null,
    playbackSpeedOptions: [0.5, 1, 2],
    playbackSpeedIndex: 1,
    playTimer: null,
    playWaitingForFrame: false,
    previewRequestId: 0,
    renderRevision: 0,
    pendingPreviewRequestId: 0,
    sequenceName: null,
    renderQueue: [],
    queuedFrames: new Set(),
    renderInFlight: false,
    activeDialogClipId: null,
    selectedClipIds: new Set(),
    suppressClipClickUntil: 0,
    previewHeight: 400,
    statusFadeTimer: null,
  };

  let resetCircleHoverState = function () {};

  const DIALOG_FIELD_DEFS = {
    start_x: { wrap: "#dlgStartXWrap", input: "#dlgStartX", defaultValue: "", read: () => Number($("#dlgStartX").val() || 0) },
    start_y: { wrap: "#dlgStartYWrap", input: "#dlgStartY", defaultValue: "", read: () => Number($("#dlgStartY").val() || 0) },
    end_x: { wrap: "#dlgEndXWrap", input: "#dlgEndX", defaultValue: "", read: () => Number($("#dlgEndX").val() || 0) },
    end_y: { wrap: "#dlgEndYWrap", input: "#dlgEndY", defaultValue: "", read: () => Number($("#dlgEndY").val() || 0) },
    center_x: { wrap: "#dlgCenterXWrap", input: "#dlgCenterX", defaultValue: "", read: () => $("#dlgCenterX").val() },
    center_y: { wrap: "#dlgCenterYWrap", input: "#dlgCenterY", defaultValue: "", read: () => $("#dlgCenterY").val() },
    start: { wrap: "#dlgStartWrap", input: "#dlgStart", defaultValue: "", read: () => Number($("#dlgStart").val() || 0) },
    end: { wrap: "#dlgEndWrap", input: "#dlgEnd", defaultValue: "", read: () => Number($("#dlgEnd").val() || 0) },
    tween_property: { wrap: "#dlgTweenPropsWrap", input: "#dlgTweenProps", defaultValue: "alpha", read: () => String($("#dlgTweenProps").val() || "alpha") },
    tween_start: { wrap: "#dlgTweenStartsWrap", input: "#dlgTweenStarts", defaultValue: "0", read: () => $("#dlgTweenStarts").val() },
    tween_end: { wrap: "#dlgTweenEndsWrap", input: "#dlgTweenEnds", defaultValue: "1", read: () => $("#dlgTweenEnds").val() },
    zoom: { wrap: "#dlgZoomWrap", input: "#dlgZoom", defaultValue: 1, read: () => Number($("#dlgZoom").val() || 1) },
    xlim_left: { wrap: "#dlgXlimLeftWrap", input: "#dlgXlimLeft", defaultValue: "", read: () => Number($("#dlgXlimLeft").val() || 0) },
    xlim_right: { wrap: "#dlgXlimRightWrap", input: "#dlgXlimRight", defaultValue: "", read: () => Number($("#dlgXlimRight").val() || 0) },
    ylim_bottom: { wrap: "#dlgYlimBottomWrap", input: "#dlgYlimBottom", defaultValue: "", read: () => Number($("#dlgYlimBottom").val() || 0) },
    ylim_top: { wrap: "#dlgYlimTopWrap", input: "#dlgYlimTop", defaultValue: "", read: () => Number($("#dlgYlimTop").val() || 0) },
    ratio_start: { wrap: "#dlgRatioStartWrap", input: "#dlgRatioStart", defaultValue: "[1, 1]", read: () => $("#dlgRatioStart").val() },
    ratio_end: { wrap: "#dlgRatioEndWrap", input: "#dlgRatioEnd", defaultValue: "[1, 1]", read: () => $("#dlgRatioEnd").val() },
    reverse: { wrap: "#dlgReverseWrap", input: "#dlgReverse", defaultValue: false, read: () => $("#dlgReverse").is(":checked") }
  };

  const DIALOG_TYPE_SCHEMAS = {
    translate: { fields: ["start_x", "start_y", "end_x", "end_y"], showObject: true },
    scale: { fields: ["start_x", "start_y", "end_x", "end_y", "center_x", "center_y"], showObject: true },
    rotate: { fields: ["start", "end", "center_x", "center_y"], showObject: true },
    tween: { fields: ["tween_property", "tween_start", "tween_end"], showObject: true },
    draw: { fields: ['reverse'], showObject: true },
    morph: { fields: [], showObject: true },
    axis_zoom: { fields: ["zoom"], showObject: false },
    axis_limits: { fields: ["xlim_left", "xlim_right", "ylim_bottom", "ylim_top"], showObject: false },
    axis_move: { fields: ["start_x", "start_y", "end_x", "end_y"], showObject: false },
    axis_alpha: { fields: ["start", "end"], showObject: false },
    fig_width_ratio: { fields: ["ratio_start", "ratio_end"], showObject: false },
    fig_height_ratio: { fields: ["ratio_start", "ratio_end"], showObject: false },
    default: { fields: [], showObject: true },
  };

  function normalizeClipTypeKey(rawType, fallbackType) {
    const text = String(rawType || fallbackType || "").trim().toLowerCase();
    if (!text) {
      return "default";
    }
    return text;
  }

  function applyDialogSchema(typeKey) {
    const schema = DIALOG_TYPE_SCHEMAS[typeKey] || DIALOG_TYPE_SCHEMAS.default;
    const visible = new Set(schema.fields || []);

    Object.keys(DIALOG_FIELD_DEFS).forEach((fieldKey) => {
      const def = DIALOG_FIELD_DEFS[fieldKey];
      $(def.wrap).toggle(visible.has(fieldKey));
    });

    $("#dlgObjectWrap").toggle(Boolean(schema.showObject));
  }

  function fillDialogFields(properties) {
    Object.keys(DIALOG_FIELD_DEFS).forEach((fieldKey) => {
      const def = DIALOG_FIELD_DEFS[fieldKey];
      const value = properties[fieldKey];
      $(def.input).val(value ?? def.defaultValue);
    });
  }

  function buildDialogFieldPayload() {
    const payload = {};
    Object.keys(DIALOG_FIELD_DEFS).forEach((fieldKey) => {
      payload[fieldKey] = DIALOG_FIELD_DEFS[fieldKey].read();
    });
    return payload;
  }

  function previewMinHeight() {
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    const currentPreviewHeight = $("#previewImage").outerHeight() || state.previewHeight;
    const appHeight = $(".app-shell").first().outerHeight(true) || $("body").outerHeight(true) || 0;
    const nonPreviewHeight = Math.max(0, appHeight - currentPreviewHeight);
    return Math.max(120, Math.round(viewportHeight - nonPreviewHeight));
  }

  function setPreviewHeight(height) {
    const minHeight = previewMinHeight();
    const maxHeight = Math.max(800, minHeight);
    const next = Math.max(minHeight, Math.min(maxHeight, Math.round(height)));
    state.previewHeight = next;
    $("#previewImage").css("height", `${next}px`);
  }

  function showStatus(message) {
    const $frameText = $("#frameText");
    if (state.statusFadeTimer) {
      clearTimeout(state.statusFadeTimer);
      state.statusFadeTimer = null;
    }

    $frameText.text(message).removeClass("is-faded");
    state.statusFadeTimer = setTimeout(() => {
      $frameText.addClass("is-faded");
      state.statusFadeTimer = null;
    }, 3000);
  }

  function apiGet(url) {
    return fetch(url).then((r) => r.json());
  }

  function apiPost(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => r.json());
  }

  function applyServerState(payload) {
    const prevRevision = state.renderRevision;
    state.trackWidth = Math.max(100, payload.trackWidth);
    state.minRowCount = Math.max(1, payload.minRowCount);
    state.rowCount = Math.max(state.minRowCount, payload.rowCount);
    state.clips = payload.clips;
    state.hasSequence = payload.hasSequence;
    state.hasPlotObjects = payload.hasPlotObjects;
    state.renderRevision = payload.renderRevision;
    state.sequenceName = payload.sequenceName;

    const existingIds = new Set(state.clips.map((c) => c.id));
    state.selectedClipIds = new Set([...state.selectedClipIds].filter((id) => existingIds.has(id)));

    if (state.renderRevision !== prevRevision) {
      const invalidateFrom = payload.invalidatedFromFrame;
      state.renderedFrames = new Set([...state.renderedFrames].filter((f) => f < invalidateFrom));
      state.renderQueue = [];
      state.queuedFrames = new Set();
      state.renderInFlight = false;
    }
  }

  function loadState() {
    state.loadingState = true;
    return apiGet("/api/state")
      .then((payload) => {
        if (payload.error) {
          showStatus(payload.error);
          return;
        }
        applyServerState(payload);
        renderTimeline();
      })
      .catch((err) => {
        showStatus(`Could not load state: ${err}`);
      })
      .finally(() => {
        state.loadingState = false;
      });
  }

  function setPlayButtonState() {
    const symbol = state.isPlaying ? "⏸" : "▶";
    const label = state.isPlaying ? "Pause" : "Play";
    $("#btnPlayPause")
      .text(symbol)
      .attr("title", `${label}`)
      .attr("aria-label", label);
  }

  function setLoopButtonState() {
    const symbol = "⟳";
    const label = state.loopEnabled ? "Loop on" : "Loop off";
    $("#btnLoop")
      .text(symbol)
      .attr("title", label)
      .attr("aria-label", label)
      .toggleClass("active", state.loopEnabled);
  }

  function setSaveButtonState() {
    const active = state.saveVideoPending || state.saveVideoInProgress;
    const label = active ? "Saving video" : "Save video";
    $("#btnSaveVideo")
      .text("⏺︎")
      .attr("title", label)
      .attr("aria-label", label)
      .toggleClass("active", active);
  }

  function stopSaveVideoMode() {
    state.saveVideoPending = false;
    state.saveVideoFileName = null;
    stopPlayback();
    setSaveButtonState();
  }

  function currentPlaybackSpeed() {
    return state.playbackSpeedOptions[state.playbackSpeedIndex];
  }

  function setSpeedButtonState() {
    const speed = currentPlaybackSpeed();
    $("#btnSpeed")
      .text(`x${speed}`)
      .attr("title", `Playback speed x${speed}`)
      .attr("aria-label", `Playback speed x${speed}`);
  }

  function setPinFrame(frame, renderNow) {
    const nextFrame = Math.max(0, Math.min(state.trackWidth, Math.round(frame)));
    const frameChanged = nextFrame !== state.pinX;
    state.pinX = nextFrame;
    refreshPinGeometry();
    if (!renderNow) {
      return;
    }

    if (frameChanged || !state.renderedFrames.has(nextFrame)) {
      updatePreview(nextFrame);
    }
  }

  function framePath(frame) {
    if (!state.sequenceName) {
      return null;
    }
    return `/frames/${state.sequenceName}_${frame}.png`;
  }

  function setPreviewImage(frame, requestId) {
    const srcPath = framePath(frame);
    if (!srcPath) {
      return;
    }
    const src = `${srcPath}?rev=${state.renderRevision}&r=${requestId}`;
    $("#previewImage")
      .attr("data-request-id", String(requestId))
      .attr("data-frame", String(frame))
      .attr("src", src);
  }

  function processRenderQueue() {
    if (state.renderInFlight) {
      return;
    }
    if (state.renderQueue.length === 0) {
      return;
    }

    const item = state.renderQueue.shift();
    state.queuedFrames.delete(item.frame);
    state.renderInFlight = true;

    apiPost("/api/render", { frame: item.frame })
      .then((payload) => {
        if (payload.error) {
          throw new Error(payload.error);
        }
        state.renderRevision = payload.renderRevision;
        markFrameRendered(item.frame);

        if (item.requestId === state.pendingPreviewRequestId) {
          setPreviewImage(item.frame, item.requestId);
        }
      })
      .catch((err) => {
        showStatus(`Render error: ${err.message || err}`);
      })
      .finally(() => {
        state.renderInFlight = false;
        processRenderQueue();
      });
  }

  function enqueueFrameRender(frame, requestId) {
    if (state.renderedFrames.has(frame)) {
      if (requestId === state.pendingPreviewRequestId) {
        setPreviewImage(frame, requestId);
      }
      return;
    }

    if (!state.queuedFrames.has(frame)) {
      state.queuedFrames.add(frame);
      state.renderQueue.push({ frame, requestId });
    } else if (requestId === state.pendingPreviewRequestId) {
      for (let i = state.renderQueue.length - 1; i >= 0; i -= 1) {
        if (state.renderQueue[i].frame === frame) {
          state.renderQueue[i].requestId = requestId;
          break;
        }
      }
    }

    processRenderQueue();
  }

  function updatePreview(frameOverride) {
    const frame = Math.round(frameOverride ?? state.pinX);

    if (!state.hasSequence || !state.hasPlotObjects) {
      showStatus("Frame preview unavailable: pass seq and plot_objects to GUI_web.GUI(...)");
      return;
    }

    state.previewRequestId += 1;
    const requestId = state.previewRequestId;
    state.pendingPreviewRequestId = requestId;

    enqueueFrameRender(frame, requestId);
  }

  function markFrameRendered(frame) {
    state.renderedFrames.add(Math.round(frame));
    renderFrameIndicators();
  }

  function renderFrameIndicators() {
    const $strip = $("#frameStrip");
    $strip.find(".frame-indicator").remove();
    state.renderedFrames.forEach((frame) => {
      if (frame < 0 || frame > state.trackWidth) {
        return;
      }
      $("<div>")
        .addClass("frame-indicator")
        .css("left", `${frame}px`)
        .appendTo($strip);
    });
  }

  function renderTimelineTicks() {
    const $ruler = $("#timelineRuler");
    if ($ruler.length === 0) {
      return;
    }

    $ruler.find(".frame-major-tick, .frame-major-label").remove();
    const visibleWidth = Math.max(state.trackWidth, Math.round($("#timeline").innerWidth() || state.trackWidth));

    for (let frame = 0; frame <= visibleWidth; frame += 60) {
      $("<div>")
        .addClass("frame-major-tick")
        .css("left", `${frame}px`)
        .appendTo($ruler);

      $("<div>")
        .addClass("frame-major-label")
        .css("left", `${frame}px`)
        .text(String(frame))
        .appendTo($ruler);
    }
  }

  function makeTrack(rowIndex) {
    return $("<div>")
      .addClass("track-row")
      .attr("data-row", rowIndex)
      .attr("data-label", `track #${rowIndex + 1}`)
  }

  function makeAddTrackBar() {
    return $("<div>")
      .addClass("add-track")
      .text("+");
  }

  function makeTrackControl(rowIndex) {
    const $control = $("<div>").addClass("track-control");
    if (rowIndex < state.minRowCount) {
      return $control;
    }
    return $control.append(
      $("<button>")
        .addClass("delete-track")
        .attr("data-row", rowIndex)
        .attr("title", `Delete track #${rowIndex + 1}`)
        .text("-")
    );
  }

  function refreshPinGeometry() {
    state.pinX = Math.max(0, Math.min(state.trackWidth, Math.round(state.pinX)));
    const timelineHeight = state.rowCount * (state.trackHeight + 2) + 28;
    $("#timelinePin").css({
      left: `${state.pinX}px`,
      height: `${timelineHeight}px`,
    });
    $("#pinHandle")
      .text(String(Math.round(state.pinX)))
      .attr("title", `Frame ${Math.round(state.pinX)}`)
      .attr("aria-label", `Current frame ${Math.round(state.pinX)}`);
    $("#pinLayer").css({
      width: `${state.trackWidth}px`,
      height: `${timelineHeight}px`,
    });
    $("#timeline").css("--timeline-width", `${state.trackWidth}px`);
    $("#frameStrip").css("width", `${state.trackWidth+4}px`);
    renderTimelineTicks();
    updateTimelineResizeHandlePosition();
  }

  function updateTimelineResizeHandlePosition() {
    const handleWidth = $("#timelineResizeHandle").outerWidth();
    const x = state.trackWidth - Math.round(handleWidth / 2) + 10;
    const h = Math.max(40, state.rowCount * (state.trackHeight - 2) - 10);
    $("#timelineResizeHandle").css({
      left: `${x}px`,
      height: `${h}px`,
    });
  }

  function renderClips() {
    $(".track-row").each(function () {
      $(this).find(".clip").remove();
    });

    state.clips.forEach((clip) => {
      const $row = $(`.track-row[data-row='${clip.row}']`);
      if ($row.length === 0) {
        return;
      }
      var clipType = clip.type.replace('_',' ');
      var clipHTML = clipType;
      if (clip.plotObjectName != "None"){
        clipHTML += '<br/><span>' + clip.plotObjectName + '</span>';
      }
      const $clip = $("<div>")
        .addClass("clip").addClass(clip.type)
        .attr("data-id", clip.id)
        .css({ left: `${clip.x}px`, width: `${clip.width}px` })
        .html(clipHTML);
      if (state.selectedClipIds.has(clip.id)) {
        $clip.addClass("selected");
      }
      makeClipDraggable($clip);
      makeClipResizable($clip);
      $row.append($clip);
    });
  }

  function refreshClipSelectionStyles() {
    $(".clip").each(function () {
      const id = $(this).attr("data-id");
      $(this).toggleClass("selected", state.selectedClipIds.has(id));
    });
  }

  function selectOnlyClip(id) {
    state.selectedClipIds = new Set([id]);
    refreshClipSelectionStyles();
  }

  function toggleClipSelection(id) {
    if (state.selectedClipIds.has(id)) {
      state.selectedClipIds.delete(id);
    } else {
      state.selectedClipIds.add(id);
    }
    refreshClipSelectionStyles();
  }

  function clearClipSelection() {
    if (state.selectedClipIds.size === 0) {
      return;
    }
    state.selectedClipIds.clear();
    refreshClipSelectionStyles();
  }

  function deleteSelectedClips() {
    if (state.selectedClipIds.size === 0) {
      return;
    }
    const ids = [...state.selectedClipIds];
    apiPost("/api/clip/delete", { ids })
      .then((payload) => {
        if (payload.error) {
          throw new Error(payload.error);
        }
        state.selectedClipIds.clear();
        applyServerState(payload.state);
        renderTimeline();
        updatePreview();
      })
      .catch((err) => {
        showStatus(`Delete clip failed: ${err.message || err}`);
      });
  }

  function calcAllowedGroupDelta(ids, delta) {
    let allowed = delta;
    ids.forEach((id) => {
      const clip = state.clips.find((c) => c.id === id);
      if (!clip) {
        return;
      }
      allowed = Math.max(allowed, -clip.x);
      allowed = Math.min(allowed, state.trackWidth - (clip.x + clip.width));
    });
    return allowed;
  }

  function renderTimeline() {
    const $timeline = $("#timeline");
    const $controls = $("#trackControls");
    $('.track-row').remove();
    $('.add-track').remove();
    $controls.empty();

    for (let i = 0; i < state.rowCount; i += 1) {
      $timeline.append(makeTrack(i));
      $controls.append(makeTrackControl(i));
    }

    $timeline.append(makeAddTrackBar());
    $controls.append($("<div>").addClass("track-controls-spacer"));
    renderClips();
    refreshPinGeometry();
    renderFrameIndicators();
    setPreviewHeight(state.previewHeight);
  }

  function addTrack() {
    state.rowCount += 1;
    renderTimeline();
    apiPost("/api/timeline/rows", { rowCount: state.rowCount })
      .then((res) => {
        if (res.error) {
          throw new Error(res.error);
        }
        applyServerState(res.state);
        renderTimeline();
      })
      .catch((err) => {
        showStatus(`Add track failed: ${err.message || err}`);
      });
  }

  function deleteTrack(rowIndex) {
    apiPost("/api/timeline/delete-row", { row: rowIndex })
      .then((res) => {
        if (res.error) {
          throw new Error(res.error);
        }
        applyServerState(res.state);
        renderTimeline();
        updatePreview();
      })
      .catch((err) => {
        showStatus(`Delete track failed: ${err.message || err}`);
      });
  }

  function placeClip(rowIndex, x, width, type) {
    if (!state.hasPlotObjects) {
      showStatus("Cannot create clip: no plot objects provided to GUI_web.GUI(...)");
      return;
    }

    apiPost("/api/clip/create", {
      type,
      row: rowIndex,
      x,
      width,
    })
      .then((payload) => {
        if (payload.error) {
          throw new Error(payload.error);
        }
        applyServerState(payload.state);
        renderTimeline();
        if (payload.clipId) {
          openClipDialog(payload.clipId);
        }
        updatePreview();
      })
      .catch((err) => {
        showStatus(`Create clip failed: ${err.message || err}`);
      });
  }

  function overlapsInRow(rowIndex, x, width, ignoreId) {
    const ignoreSet = new Set();
    if (Array.isArray(ignoreId)) {
      ignoreId.forEach((value) => ignoreSet.add(String(value)));
    } else if (ignoreId !== undefined && ignoreId !== null) {
      ignoreSet.add(String(ignoreId));
    }

    const left = x;
    const right = x + width;
    return state.clips.some((clip) => {
      if (clip.row !== rowIndex) {
        return false;
      }
      if (ignoreSet.has(String(clip.id))) {
        return false;
      }
      const cLeft = clip.x;
      const cRight = clip.x + clip.width;
      return left < cRight && right > cLeft;
    });
  }

  function rowFromClientY(clientY) {
    const timelineEl = $("#timeline")[0];
    if (!timelineEl) {
      return 0;
    }

    const timelineRect = timelineEl.getBoundingClientRect();
    const rowSpan = state.trackHeight + 2;
    const rawRow = Math.floor((clientY - timelineRect.top) / rowSpan);
    return Math.max(0, Math.min(Math.max(0, state.rowCount - 1), rawRow));
  }

  function blockingClipsInRow(rowIndex, x, width, ignoreId) {
    const ignoreSet = new Set();
    if (Array.isArray(ignoreId)) {
      ignoreId.forEach((value) => ignoreSet.add(String(value)));
    } else if (ignoreId !== undefined && ignoreId !== null) {
      ignoreSet.add(String(ignoreId));
    }

    const left = x;
    const right = x + width;
    return state.clips.filter((clip) => {
      if (clip.row !== rowIndex) {
        return false;
      }
      if (ignoreSet.has(String(clip.id))) {
        return false;
      }
      const cLeft = clip.x;
      const cRight = clip.x + clip.width;
      return left < cRight && right > cLeft;
    });
  }

  function resolveDropLeft(rowIndex, width, desiredLeft, ignoreId, alreadyResolvedMoves) {
    const minLeft = 0;
    const maxLeft = Math.max(0, state.trackWidth - width);
    const clampedDesired = Math.max(minLeft, Math.min(maxLeft, Math.round(desiredLeft)));
    
    const occupiedRanges = [];
    if (alreadyResolvedMoves) {
      alreadyResolvedMoves.forEach((move) => {
        if (move.nextRow === rowIndex) {
          occupiedRanges.push({ left: move.nextLeft, right: move.nextLeft + move.clip.width });
        }
      });
    }

    function isBlockedByResolved(left, right) {
      return occupiedRanges.some((range) => left < range.right && right > range.left);
    }

    if (!overlapsInRow(rowIndex, clampedDesired, width, ignoreId) && !isBlockedByResolved(clampedDesired, clampedDesired + width)) {
      return clampedDesired;
    }

    const candidates = [];
    blockingClipsInRow(rowIndex, clampedDesired, width, ignoreId).forEach((clip) => {
      const leftSide = clip.x - width;
      const rightSide = clip.x + clip.width;
      if (leftSide >= minLeft && !overlapsInRow(rowIndex, leftSide, width, ignoreId) && !isBlockedByResolved(leftSide, leftSide + width)) {
        candidates.push(leftSide);
      }
      if (rightSide <= maxLeft && !overlapsInRow(rowIndex, rightSide, width, ignoreId) && !isBlockedByResolved(rightSide, rightSide + width)) {
        candidates.push(rightSide);
      }
    });

    if (candidates.length === 0) {
      return null;
    }

    candidates.sort((a, b) => {
      const da = Math.abs(a - clampedDesired);
      const db = Math.abs(b - clampedDesired);
      if (da !== db) {
        return da - db;
      }
      return a - b;
    });

    return candidates[0];
  }

  function findAvailableRow(x, width) {
    for (let row = 0; row < state.rowCount; row += 1) {
      if (!overlapsInRow(row, x, width)) {
        return row;
      }
    }
    addTrack();
    return state.rowCount - 1;
  }

  function makeClipDraggable($clip) {
    const id = $clip.attr("data-id");
    let dragging = false;
    let moved = false;
    let startX = 0;
    let startRow = 0;
    let dragIds = [];
    let originLeftById = {};
    let originRowById = {};
    let originClipStateById = {};
    const resizeHandlePx = 6;

    function applyGroupPreview(deltaX, rowDelta) {
      dragIds.forEach((dragId) => {
        const left = originLeftById[dragId] + deltaX;
        const originRow = originRowById[dragId] ?? 0;
        const previewRow = Math.max(0, Math.min(Math.max(0, state.rowCount - 1), originRow + rowDelta));
        const $clipEl = $(`.clip[data-id='${dragId}']`);
        const $row = $(`.track-row[data-row='${previewRow}']`);
        if ($clipEl.length > 0 && $row.length > 0 && $clipEl.parent()[0] !== $row[0]) {
          $row.append($clipEl);
        }
        $clipEl.css("left", `${left}px`);
      });
    }

    $clip.on("mousedown", function (event) {
      const clipLeft = $clip.offset().left;
      const localX = event.pageX - clipLeft;
      const clipWidth = $clip.outerWidth();
      if (localX <= resizeHandlePx || localX >= clipWidth - resizeHandlePx) {
        return;
      }

      const additive = event.shiftKey || event.metaKey || event.ctrlKey;
      if (additive) {
        toggleClipSelection(id);
      } else if (!state.selectedClipIds.has(id)) {
        selectOnlyClip(id);
      }

      dragIds = state.selectedClipIds.has(id) ? [...state.selectedClipIds] : [id];
      if (dragIds.length === 0) {
        dragIds = [id];
      }

      originLeftById = {};
      originRowById = {};
      originClipStateById = {};
      dragIds.forEach((dragId) => {
        const dragClip = state.clips.find((c) => c.id === dragId);
        if (!dragClip) {
          return;
        }
        originLeftById[dragId] = dragClip.x;
        originRowById[dragId] = dragClip.row;
        originClipStateById[dragId] = { ...dragClip };
      });

      dragging = true;
      moved = false;
      startX = event.pageX;
      startRow = rowFromClientY(event.clientY);
      state.suppressClipClickUntil = Date.now() + 150;
      event.preventDefault();
    });

    $(document).on(`mousemove.clipDrag.${id}`, function (event) {
      if (!dragging) {
        return;
      }
      const rawDelta = Math.round(event.pageX - startX);
      if (Math.abs(rawDelta) >= 2) {
        moved = true;
      }
      const delta = calcAllowedGroupDelta(dragIds, rawDelta);
      const currentRow = rowFromClientY(event.clientY);
      applyGroupPreview(delta, currentRow - startRow);
    });

    $(document).on(`mouseup.clipDrag.${id}`, function (event) {
      if (!dragging) {
        return;
      }
      dragging = false;

      if (moved) {
        state.suppressClipClickUntil = Date.now() + 150;
      }

      const anchorLeft = parseFloat($(`.clip[data-id='${id}']`).css("left"));
      const anchorOrigin = originLeftById[id] ?? anchorLeft;
      const snappedAnchorLeft = Math.round(anchorLeft / 10) * 10;
      const snappedDelta = snappedAnchorLeft - anchorOrigin;
      const finalDelta = calcAllowedGroupDelta(dragIds, snappedDelta);
      const finalRowDelta = rowFromClientY(event.clientY) - startRow;

      const idSet = new Set(dragIds);
      const resolvedMoves = [];
      let valid = true;
      dragIds.forEach((dragId) => {
        const clip = originClipStateById[dragId];
        if (!clip) {
          return;
        }
        const nextRow = Math.max(0, (originRowById[dragId] ?? clip.row) + finalRowDelta);
        const desiredLeft = clip.x + finalDelta;
        const resolvedLeft = resolveDropLeft(nextRow, clip.width, desiredLeft, dragId, resolvedMoves);
        if (resolvedLeft === null) {
          valid = false;
          return;
        }
        resolvedMoves.push({ clip, nextLeft: resolvedLeft, nextRow });
      });

      if (!valid) {
        renderTimeline();
        return;
      }

      const updates = resolvedMoves.map(({ clip, nextLeft, nextRow }) => {
        return apiPost("/api/clip/update", {
          id: clip.id,
          x: nextLeft,
          width: clip.width,
          row: nextRow,
        });
      });

      Promise.all(updates)
        .then((results) => {
          const last = results[results.length - 1];
          if (!last || last.error) {
            throw new Error(last?.error || "Update failed");
          }
          applyServerState(last.state);
          renderTimeline();
          updatePreview();
        })
        .catch((err) => {
          showStatus(`Update clip failed: ${err.message || err}`);
          renderTimeline();
        });
    });
  }

  function makeClipResizable($clip) {
    const id = $clip.attr("data-id");
    let resizing = false;
    let resized = false;
    let side = null;
    let startX = 0;
    let startLeft = 0;
    let startWidth = 0;

    $clip.on("mousemove", function (event) {
      if (resizing) {
        return;
      }
      const x = event.offsetX;
      const w = $clip.outerWidth();
      $clip.removeClass("resize-left resize-right");
      if (x <= 6) {
        $clip.addClass("resize-left");
      } else if (x >= w - 6) {
        $clip.addClass("resize-right");
      }
    });

    $clip.on("mousedown", function (event) {
      const x = event.offsetX;
      const w = $clip.outerWidth();
      if (!(x <= 6 || x >= w - 6)) {
        return;
      }
      resizing = true;
      resized = false;
      side = x <= 6 ? "left" : "right";
      startX = event.pageX;
      startLeft = parseFloat($clip.css("left"));
      startWidth = $clip.outerWidth();
      event.stopPropagation();
      event.preventDefault();
    });

    $(document).on(`mousemove.clipResize.${id}`, function (event) {
      if (!resizing) {
        return;
      }
      const delta = event.pageX - startX;
      if (Math.abs(delta) >= 2) {
        resized = true;
      }
      let nextLeft = startLeft;
      let nextWidth = startWidth;

      if (side === "left") {
        nextLeft = Math.max(0, Math.min(startLeft + delta, startLeft + startWidth - 1));
        nextWidth = Math.max(1, startWidth - (nextLeft - startLeft));
      } else {
        nextWidth = Math.max(1, Math.min(startWidth + delta, state.trackWidth - startLeft));
      }

      $clip.css({ left: `${Math.round(nextLeft)}px`, width: `${Math.round(nextWidth)}px` });
    });

    $(document).on(`mouseup.clipResize.${id}`, function () {
      if (!resizing) {
        return;
      }
      resizing = false;
      if (resized) {
        state.suppressClipClickUntil = Date.now() + 150;
      }
      const clip = state.clips.find((c) => c.id === id);
      if (!clip) {
        return;
      }

      const nextLeft = Math.max(0, Math.round(parseFloat($clip.css("left"))));
      const nextWidth = Math.max(1, Math.round($clip.outerWidth()));

      if (!overlapsInRow(clip.row, nextLeft, nextWidth, clip.id)) {
        apiPost("/api/clip/update", {
          id: clip.id,
          x: nextLeft,
          width: nextWidth,
          row: clip.row,
        })
          .then((payload) => {
            if (payload.error) {
              throw new Error(payload.error);
            }
            const invalidateFrom = Math.min(clip.x, nextLeft);
            state.renderedFrames = new Set([...state.renderedFrames].filter((f) => f < invalidateFrom));
            applyServerState(payload.state);
            renderTimeline();
            updatePreview();
          })
          .catch((err) => {
            showStatus(`Resize failed: ${err.message || err}`);
            renderTimeline();
          });
      } else {
        renderTimeline();
      }
    });
  }

  function openClipDialog(clipId) {
    apiPost("/api/clip/get", { id: clipId })
      .then((payload) => {
        if (payload.error) {
          throw new Error(payload.error);
        }
        const p = payload.properties;
        state.activeDialogClipId = clipId;
        $("#dlgDelay").val(p.delay ?? 0);
        $("#dlgDuration").val(p.duration ?? 1);
        $("#dlgPersistent").prop("checked", Boolean(p.persistent));

        const $e = $("#dlgEasing");
        $e.empty();
        (p.availableEasings || []).forEach((name) => {
          const opt = $("<option>").attr("value", name).text(name);
          if (name === p.easing) {
            opt.attr("selected", "selected");
          }
          $e.append(opt);
        });

        const $obj = $("#dlgObject");
        $obj.empty();
        (p.plotObjectOptions || []).forEach((opt) => {
          const $opt = $("<option>").attr("value", String(opt.id)).text(opt.name);
          if (Number(opt.id) === Number(p.plotObjectId)) {
            $opt.attr("selected", "selected");
          }
          $obj.append($opt);
        });

        const typeKey = normalizeClipTypeKey(p.typeKey, p.type);
        applyDialogSchema(typeKey);
        fillDialogFields(p);

        $("#clipDialogBackdrop").removeClass("hidden");
      })
      .catch((err) => {
        showStatus(`Open properties failed: ${err.message || err}`);
      });
  }

  function closeClipDialog() {
    state.activeDialogClipId = null;
    $("#clipDialogBackdrop").addClass("hidden");
  }

  function saveClipDialog() {
    if (!state.activeDialogClipId) {
      return;
    }
    const payload = {
      id: state.activeDialogClipId,
      delay: Number($("#dlgDelay").val() || 0),
      duration: Number($("#dlgDuration").val() || 1),
      easing: $("#dlgEasing").val(),
      persistent: $("#dlgPersistent").is(":checked"),
      plotObjectId: Number($("#dlgObject").val() || 0),
      ...buildDialogFieldPayload(),
    };

    apiPost("/api/clip/properties", payload)
      .then((res) => {
        if (res.error) {
          throw new Error(res.error);
        }
        applyServerState(res.state);
        renderTimeline();
        updatePreview();
        closeClipDialog();
      })
      .catch((err) => {
        showStatus(`Save properties failed: ${err.message || err}`);
      });
  }

  function setPinFromClientX(clientX) {
    const stripRect = $("#frameStrip")[0].getBoundingClientRect();
    const x = Math.round(clientX - stripRect.left);
    setPinFrame(x, true);
  }

  function playStep() {
    if (!state.isPlaying) {
      return;
    }
    if (state.playWaitingForFrame) {
      return;
    }

    const currentFrame = Math.round(state.pinX);
    if (currentFrame >= state.trackWidth) {
      if (state.saveVideoPending) {
        finishSaveVideo();
        return;
      }
      if (state.loopEnabled) {
        state.playWaitingForFrame = true;
        setPinFrame(0, true);
        return;
      }
      stopPlayback();
      return;
    }

    const next = Math.min(state.trackWidth, currentFrame + 1);
    state.playWaitingForFrame = true;
    setPinFrame(next, true);
  }

  function finishSaveVideo() {
    if (state.saveVideoInProgress) {
      return;
    }
    state.saveVideoInProgress = true;
    setSaveButtonState();
    stopPlayback();
    showStatus("Preparing video file...");

    apiPost("/api/save-video-temp", { timelineWidth: state.trackWidth })
      .then((res) => {
        if (res.error) {
          throw new Error(res.error);
        }
        const token = String(res.token || "");
        const serverFilename = String(res.filename || `${state.sequenceName || "video"}.mp4`);
        if (!token) {
          throw new Error("Missing export token.");
        }

        let targetName = state.saveVideoFileName || serverFilename;
        if (!targetName.includes(".") && serverFilename.includes(".")) {
          targetName += `.${serverFilename.split(".").pop()}`;
        }

        return fetch(`/api/save-video-file?token=${encodeURIComponent(token)}`)
          .then((r) => {
            if (!r.ok) {
              throw new Error(`Download failed (${r.status})`);
            }
            return r.blob();
          })
          .then((blob) => {
            downloadBlob(blob, targetName);
            return targetName;
          });
      })
      .then((savedAs) => {
        showStatus(`Saved video: ${savedAs}`);
      })
      .catch((err) => {
        showStatus(`Save video failed: ${err.message || err}`);
      })
      .finally(() => {
        state.saveVideoPending = false;
        state.saveVideoInProgress = false;
        state.saveVideoFileName = null;
        setSaveButtonState();
      });
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function clearRenderedFrames() {
    stopPlayback();
    state.renderedFrames = new Set();
    state.pinX = 0;
    $("#previewImage").attr("src", "src/logo_bg.png");
    loadState().then(() => {
      renderTimeline();
    });
  }

  function restartPlayTimer() {
    if (state.playTimer) {
      clearInterval(state.playTimer);
      state.playTimer = null;
    }
    const fps = 30 * 3 * currentPlaybackSpeed();
    state.playTimer = setInterval(playStep, 1000 / fps);
  }

  function startPlayback() {
    if (state.isPlaying) {
      return;
    }
    if (Math.round(state.pinX) >= state.trackWidth) {
      setPinFrame(0, true);
    }
    state.isPlaying = true;
    state.playWaitingForFrame = false;
    setPlayButtonState();
    restartPlayTimer();
  }

  function stopPlayback() {
    state.isPlaying = false;
    state.playWaitingForFrame = false;
    setPlayButtonState();
    if (state.playTimer) {
      clearInterval(state.playTimer);
      state.playTimer = null;
    }
  }

  function loadDemoProject() {
    loadState().then(() => {
      showStatus("Loaded timeline state from Python objects.");
      updatePreview();
    });
  }

  function paletteInternalType($item) {
    const dataType = String($item.attr("data-type") || "").trim();
    if (dataType) {
      return dataType;
    }
    return String($item.text() || "Clip").trim();
  }

  function enablePaletteDragDrop() {
    $(document).on("dragstart", ".palette-item", function (event) {
      const type = paletteInternalType($(this));
      event.originalEvent.dataTransfer.setData("text/plain", type);
      event.originalEvent.dataTransfer.effectAllowed = "copy";
    });

    $(document).on("dragover", ".track-row", function (event) {
      event.preventDefault();
      event.originalEvent.dataTransfer.dropEffect = "copy";
    });

    $(document).on("drop", ".track-row", function (event) {
      event.preventDefault();
      const type = event.originalEvent.dataTransfer.getData("text/plain") || "Clip";
      const row = Number($(this).attr("data-row"));
      const rowRect = this.getBoundingClientRect();
      const width = 120;
      const x = Math.max(0, Math.min(Math.round(event.originalEvent.clientX - rowRect.left - width / 2), state.trackWidth - width));

      if (overlapsInRow(row, x, width)) {
        const fallbackRow = findAvailableRow(x, width);
        placeClip(fallbackRow, x, width, type);
      } else {
        placeClip(row, x, width, type);
      }
    });
  }

  function bindEvents() {
    enablePaletteDragDrop();

    let previewResizing = false;
    let previewResizeStartY = 0;
    let previewResizeStartHeight = state.previewHeight;

    $("#previewResizeHandle").on("mousedown", function (event) {
      previewResizing = true;
      previewResizeStartY = event.pageY;
      previewResizeStartHeight = state.previewHeight;
      event.preventDefault();
    });

    $("#pinHandle").on("mousedown", function (event) {
      state.pinDragging = true;
      event.preventDefault();
    });

    $(document).on("mousemove", function (event) {
      if (previewResizing) {
        const deltaY = event.pageY - previewResizeStartY;
        setPreviewHeight(previewResizeStartHeight + deltaY);
      }
      if (!state.pinDragging) {
        return;
      }
      stopPlayback();
      setPinFromClientX(event.clientX);
    });

    $(document).on("mouseup", function () {
      previewResizing = false;
      if (state.pinDragging) {
        markFrameRendered(state.pinX);
      }
      state.pinDragging = false;
    });

    $("#frameStrip").on("click", function (event) {
      stopPlayback();
      setPinFromClientX(event.clientX);
      markFrameRendered(state.pinX);
    });

    $("#btnToStart").on("click", function () {
      stopPlayback();
      setPinFrame(0, true);
      markFrameRendered(state.pinX);
    });

    $("#btnPrev").on("click", function () {
      stopPlayback();
      setPinFrame(Math.round(state.pinX) - 1, true);
      markFrameRendered(state.pinX);
    });

    $("#btnPlayPause").on("click", function () {
      if (state.isPlaying) {
        stopPlayback();
      } else {
        startPlayback();
      }
    });

    $("#btnLoop").on("click", function () {
      state.loopEnabled = !state.loopEnabled;
      setLoopButtonState();
    });

    $("#btnNext").on("click", function () {
      stopPlayback();
      setPinFrame(Math.round(state.pinX) + 1, true);
      markFrameRendered(state.pinX);
    });

    $("#btnToEnd").on("click", function () {
      stopPlayback();
      setPinFrame(state.trackWidth, true);
      markFrameRendered(state.pinX);
    });

    $("#btnSpeed").on("click", function () {
      state.playbackSpeedIndex = (state.playbackSpeedIndex + 1) % state.playbackSpeedOptions.length;
      setSpeedButtonState();
      if (state.isPlaying) {
        restartPlayTimer();
      }
    });

    $("#btnSaveVideo").on("click", function () {
      if (state.saveVideoPending || state.saveVideoInProgress) {
        stopSaveVideoMode();
        return;
      }

      if (!state.hasSequence || !state.hasPlotObjects) {
        showStatus("Save unavailable: pass seq and plot_objects to GUI_web.GUI(...)");
        return;
      }

      const suggested = `${state.sequenceName || "video"}.mp4`;
      const input = window.prompt("Enter output file name:", suggested);
      if (!input || !String(input).trim()) {
        showStatus("Save canceled.");
        return;
      }

      state.saveVideoFileName = String(input).trim();
      state.saveVideoPending = true;
      setSaveButtonState();
      stopPlayback();
      setPinFrame(0, true);
      showStatus("Rendering timeline before save...");
      startPlayback();
    });

    $("#btnSaveProject").on("click", function () {
      if (!state.hasSequence) {
        showStatus("Save project unavailable: pass seq to GUI_web.GUI(...)");
        return;
      }

      const suggested = `${state.sequenceName || "project"}.dpl`;
      const input = window.prompt("Enter project file name:", suggested);
      if (!input || !String(input).trim()) {
        showStatus("Save project canceled.");
        return;
      }

      apiPost("/api/save-project", { filename: String(input).trim() })
        .then((res) => {
          if (res.error) {
            throw new Error(res.error);
          }
          const savedPath = String(res.filename || input.trim());
          const downloadName = savedPath.split(/[\\/]/).pop() || input.trim();

          return fetch(`/api/save-project-file?filename=${encodeURIComponent(savedPath)}`)
            .then((r) => {
              if (!r.ok) {
                throw new Error(`Download failed (${r.status})`);
              }
              return r.blob();
            })
            .then((blob) => {
              downloadBlob(blob, downloadName);
              showStatus(`Saved project: ${downloadName}`);
            });
        })
        .catch((err) => {
          showStatus(`Save project failed: ${err.message || err}`);
        });
    });

    $("#btnClearFrames").on("click", function () {
      clearRenderedFrames();
    });

    $(document).on("click", ".add-track", function () {
      addTrack();
    });

    $(document).on("click", ".delete-track", function () {
      const row = Number($(this).attr("data-row"));
      deleteTrack(row);
    });

    $(document).on("click", ".clip", function (event) {
      if (Date.now() < state.suppressClipClickUntil) {
        event.stopPropagation();
        return;
      }
      const id = $(this).attr("data-id");
      const additive = event.shiftKey || event.metaKey || event.ctrlKey;
      if (additive) {
        toggleClipSelection(id);
      } else {
        selectOnlyClip(id);
      }
      event.stopPropagation();
    });

    $(document).on("click", ".track-row, #timeline, #timelineViewport", function (event) {
      if ($(event.target).closest(".clip").length === 0) {
        clearClipSelection();
      }
    });

    $(document).on("keydown", function (event) {
      const dialogOpen = !$("#clipDialogBackdrop").hasClass("hidden") && Boolean(state.activeDialogClipId);
      if (dialogOpen) {
        if (event.key === "Escape") {
          event.preventDefault();
          closeClipDialog();
          return;
        }
        if (event.key === "Enter") {
          event.preventDefault();
          saveClipDialog();
          return;
        }
      }

      if (event.target && ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName)) {
        return;
      }
      if (event.key === "Delete" || event.key === "Backspace") {
        if (state.selectedClipIds.size > 0) {
          event.preventDefault();
          deleteSelectedClips();
        }
      }
    });

    $(document).on("dblclick", ".clip", function () {
      const id = $(this).attr("data-id");
      openClipDialog(id);
    });

    let timelineResizing = false;
    let timelineStartX = 0;
    let timelineStartWidth = 0;
    $("#timelineResizeHandle").on("mousedown", function (event) {
      timelineResizing = true;
      timelineStartX = event.pageX;
      timelineStartWidth = state.trackWidth;
      event.preventDefault();
    });

    $(document).on("mousemove", function (event) {
      if (!timelineResizing) {
        return;
      }
      const dx = event.pageX - timelineStartX;
      const w = Math.max(100, Math.round(timelineStartWidth + dx));
      state.trackWidth = w;
      renderTimeline();
    });

    $(document).on("mouseup", function () {
      if (!timelineResizing) {
        return;
      }
      timelineResizing = false;
      apiPost("/api/timeline/width", { width: state.trackWidth, rowCount: state.rowCount })
        .then((res) => {
          if (res.error) {
            throw new Error(res.error);
          }
          applyServerState(res.state);
          renderTimeline();
        })
        .catch((err) => {
          showStatus(`Timeline resize failed: ${err.message || err}`);
        });
    });

    $("#dlgCancel").on("click", function () {
      closeClipDialog();
    });

    $("#dlgSave").on("click", function () {
      saveClipDialog();
    });

    $("#clipDialogBackdrop").on("click", function (event) {
      if (event.target === this) {
        closeClipDialog();
      }
    });

    $("#clearAll").on("click", function () {
      clearRenderedFrames();
    });

    $("#loadDemo").on("click", function () {
      loadDemoProject();
    });

    $(window).on("resize", function () {
      setPreviewHeight(state.previewHeight);
      renderTimelineTicks();
    });

    $("#previewImage").on("load", function () {
      const requestId = Number($(this).attr("data-request-id") || 0);
      const frame = Number($(this).attr("data-frame") || 0);
      if (requestId !== state.pendingPreviewRequestId) {
        return;
      }
      markFrameRendered(frame);
      //showStatus(`Frame: ${frame}`);
      if (state.isPlaying) {
        state.playWaitingForFrame = false;
      }
    });

    $("#previewImage").on("error", function () {
      const requestId = Number($(this).attr("data-request-id") || 0);
      if (requestId !== state.pendingPreviewRequestId) {
        return;
      }
      showStatus("Render error: could not load frame image");
      if (state.isPlaying) {
        state.playWaitingForFrame = false;
      }
    });
  }

  function initCircleInteraction() {
    const $circle = $(".circle");
    if ($circle.length === 0) {
      return;
    }

    const defaultColor = "gray";
    const defaultOpacity = 0.1;

    const circle = {
      currentX: 0,
      currentY: 0,
      targetX: 0,
      targetY: 0,
      easing: 0.22,
      animationFrame: null,
      
      init() {
        $(document).on("mousemove", (e) => {
          this.targetX = e.clientX;
          this.targetY = e.clientY;
          this.updateStateFromPosition(e);
        });
        this.animate();
      },
      
      animate() {
        this.currentX += (this.targetX - this.currentX) * this.easing;
        this.currentY += (this.targetY - this.currentY) * this.easing;
        
        $circle.css({
          left: Math.round(this.currentX) + "px",
          top: Math.round(this.currentY) + "px"
        });
        
        this.animationFrame = requestAnimationFrame(() => this.animate());
      },
      
      updateStateFromPosition(e) {
        const elementAtMouse = document.elementFromPoint(e.clientX, e.clientY);
        
        if (!elementAtMouse) {
          this.setDefaultState();
          return;
        }
        
        const $clipOrPalette = $(elementAtMouse).closest(".clip, .palette-item");
        if ($clipOrPalette.length > 0) {
          const color = window.getComputedStyle($clipOrPalette[0]).backgroundColor;
          $circle.css("background-color", color);
          $circle.css("opacity", 0.25);
          return;
        }
        
        const $button = $(elementAtMouse).closest(".timeline-controls button");
        if ($button.length > 0) {
          $circle.css("opacity", 0.25);
          return;
        }
        
        this.setDefaultState();
      },
      
      setDefaultState() {
        $circle.css("background-color", defaultColor);
        $circle.css("opacity", defaultOpacity);
      }
    };
    
    resetCircleHoverState = function () {
      circle.setDefaultState();
    };
    
    circle.init();
  }

  $(function () {
    setPreviewHeight(state.previewHeight);
    $("#previewImage").attr("src", "src/logo_bg.png");
    bindEvents();
    setPlayButtonState();
    setLoopButtonState();
    setSaveButtonState();
    setSpeedButtonState();
    initCircleInteraction();
    loadState().then(() => {
    });
  });
})();
