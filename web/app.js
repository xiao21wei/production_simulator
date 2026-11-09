const STATUS_TEXT = {
  idle: "等待启动",
  preparing: "准备数据",
  running: "仿真运行中",
  reoptimizing: "重调度中 · 仿真已暂停",
  finished: "仿真完成",
  failed: "运行失败",
};

const EVENT_TEXT = {
  OperationStartEvent: "工序开始",
  OperationFinishEvent: "工序完成",
  TransportFinishEvent: "运输完成",
  JobSubmitEvent: "作业提交",
  JobStartEvent: "作业开始",
  JobFinishEvent: "作业完成",
  ScheduleEvent: "生成排程",
};

const elements = {
  autoJobSubmit: document.querySelector("#auto-job-submit"),
  clockReadout: document.querySelector("#clock-readout"),
  connectionStatus: document.querySelector("#connection-status"),
  currentTime: document.querySelector("#current-time"),
  datasetSelect: document.querySelector("#dataset-select"),
  deliveryPenalty: document.querySelector("#delivery-penalty"),
  displaySelect: document.querySelector("#display-select"),
  errorBanner: document.querySelector("#error-banner"),
  eventCount: document.querySelector("#event-count"),
  eventList: document.querySelector("#event-list"),
  finishedJobs: document.querySelector("#finished-jobs"),
  manualJobInsertButton: document.querySelector(
    "#manual-job-insert-button"
  ),
  machineLanes: document.querySelector("#machine-lanes"),
  makespan: document.querySelector("#makespan"),
  playhead: document.querySelector("#playhead"),
  reoptimizeButton: document.querySelector("#reoptimize-button"),
  reoptimizerSelect: document.querySelector("#reoptimizer-select"),
  speedSelect: document.querySelector("#speed-select"),
  startButton: document.querySelector("#start-button"),
  timeAxis: document.querySelector("#time-axis"),
  timelineBody: document.querySelector("#timeline-body"),
  totalEnergy: document.querySelector("#total-energy"),
};

const app = {
  after: 0,
  generation: null,
  horizon: 100,
  visibleSpan: 100,
  currentTime: 0,
  serverTime: 0,
  lastServerTime: 0,
  lastSyncAt: performance.now(),
  lastAxisRenderAt: 0,
  lastFrameRenderAt: 0,
  datasetsReady: false,
  displayPercent: 100,
  speed: 5,
  status: "idle",
  lanes: new Map(),
  bars: new Map(),
  transportSegments: new Map(),
  nextOperationStart: new Map(),
  pendingSignatures: new Map(),
  eventCount: 0,
};
let pollTimer = null;

function formatTime(value) {
  return Number(value || 0).toFixed(value < 10 ? 1 : 0);
}

function operationKey(jobId, operationId) {
  return `${jobId}-${operationId}`;
}

function jobHue(jobId) {
  return (185 + Number(jobId) * 137.508) % 360;
}

function resetView() {
  app.after = 0;
  app.lanes.clear();
  app.bars.clear();
  app.transportSegments.clear();
  app.nextOperationStart.clear();
  app.pendingSignatures.clear();
  app.eventCount = 0;
  app.horizon = 100;
  app.visibleSpan = 100;
  app.currentTime = 0;
  app.serverTime = 0;
  app.lastServerTime = 0;
  app.lastSyncAt = performance.now();
  app.lastAxisRenderAt = 0;
  app.lastFrameRenderAt = 0;
  app.displayPercent = 100;
  elements.machineLanes.replaceChildren();
  elements.eventList.replaceChildren();
  elements.eventCount.textContent = "0";
  elements.timelineBody.scrollTop = 0;
}

function enableTimelineWheelScroll() {
  elements.timelineBody.addEventListener(
    "wheel",
    (event) => {
      const maxScroll =
        elements.timelineBody.scrollHeight
        - elements.timelineBody.clientHeight;
      if (maxScroll <= 0 || event.ctrlKey) {
        return;
      }
      event.preventDefault();
      elements.timelineBody.scrollTop = Math.max(
        0,
        Math.min(maxScroll, elements.timelineBody.scrollTop + event.deltaY),
      );
    },
    { passive: false },
  );
}

function ensureLane(machineId) {
  if (app.lanes.has(machineId)) {
    return app.lanes.get(machineId);
  }

  const lane = document.createElement("div");
  lane.className = "machine-lane";

  const label = document.createElement("div");
  label.className = "machine-label";
  label.innerHTML = `<strong>M${String(machineId).padStart(2, "0")}</strong><span></span>`;

  const track = document.createElement("div");
  track.className = "machine-lane-track";
  const pendingQueue = document.createElement("div");
  pendingQueue.className = "pending-queue";
  lane.append(label, track, pendingQueue);

  const nextMachineId = [...app.lanes.keys()]
    .filter((id) => id > machineId)
    .sort((left, right) => left - right)[0];
  if (nextMachineId === undefined) {
    elements.machineLanes.append(lane);
  } else {
    elements.machineLanes.insertBefore(
      lane,
      app.lanes.get(nextMachineId).lane,
    );
  }

  const entry = {
    lane,
    label,
    track,
    pendingQueue,
    status: label.querySelector("span"),
  };
  app.lanes.set(machineId, entry);
  return entry;
}

function ensureBar(operation) {
  const key = operationKey(operation.job_id, operation.operation_id);
  let bar = app.bars.get(key);
  const lane = ensureLane(operation.machine_id);
  if (!bar) {
    bar = document.createElement("div");
    bar.className = "operation-bar";
    bar.style.setProperty("--bar-hue", jobHue(operation.job_id));
    bar.dataset.key = key;
    bar.dataset.start = operation.start_time;
    bar.dataset.end = operation.end_time;
    bar.dataset.machine = operation.machine_id;
    bar.textContent = `J${operation.job_id}-O${operation.operation_id}`;
    bar.title =
      `作业 ${operation.job_id} / 工序 ${operation.operation_id} / `
      + `M${operation.machine_id} / ${operation.start_time}-${operation.end_time}`;
    lane.track.append(bar);
    app.bars.set(key, bar);
  }
  positionBar(bar);
  return bar;
}

function positionBar(bar) {
  const start = Number(bar.dataset.start);
  const end = Number(bar.dataset.end);
  const startOffset = start - app.currentTime;
  const endOffset = end - app.currentTime;
  const halfSpan = app.visibleSpan / 2;
  const outside = endOffset < -halfSpan || startOffset > halfSpan;
  bar.hidden = outside;
  if (outside) {
    return;
  }

  const left = 50 + (startOffset / app.visibleSpan) * 100;
  const actualWidth = ((end - start) / app.visibleSpan) * 100;
  const nextStart = app.nextOperationStart.get(bar.dataset.key);
  const availableWidth = nextStart === undefined
    ? Number.POSITIVE_INFINITY
    : ((nextStart - start) / app.visibleSpan) * 100;
  const width = Math.max(
    actualWidth,
    Math.min(2.8, Math.max(0, availableWidth)),
  );
  const leftValue = `${left}%`;
  const widthValue = `${width}%`;
  if (bar.style.left !== leftValue) {
    bar.style.left = leftValue;
  }
  if (bar.style.width !== widthValue) {
    bar.style.width = widthValue;
  }
}

function ensureTransportSegment(operation) {
  const key = operationKey(operation.job_id, operation.operation_id);
  let segment = app.transportSegments.get(key);
  const lane = ensureLane(operation.machine_id);
  if (!segment) {
    segment = document.createElement("div");
    segment.className = "transport-segment";
    app.transportSegments.set(key, segment);
  }

  if (segment.parentElement !== lane.track) {
    lane.track.append(segment);
  }
  segment.dataset.start = operation.transport_start;
  segment.dataset.end = operation.transport_end;
  segment.dataset.sourceMachine = operation.source_machine;
  segment.dataset.targetMachine = operation.machine_id;
  segment.style.setProperty("--bar-hue", jobHue(operation.job_id));
  segment.textContent =
    `M${operation.source_machine}→M${operation.machine_id}`;
  segment.title =
    `机器间运输：M${operation.source_machine} → M${operation.machine_id} / `
    + `运输时间 ${operation.transport_time} / `
    + `运输能耗 ${operation.transport_energy} / `
    + `目标机器等待 ${operation.waiting_time}`;
  return segment;
}

function syncTransportPlan(plan) {
  const desiredKeys = new Set();
  for (const operation of plan || []) {
    if (
      operation.transport_time > 0
      && operation.transport_start !== null
      && operation.transport_end !== null
    ) {
      const key = operationKey(
        operation.job_id,
        operation.operation_id,
      );
      desiredKeys.add(key);
      ensureTransportSegment(operation);
    }
  }
  for (const [key, segment] of app.transportSegments.entries()) {
    if (!desiredKeys.has(key)) {
      segment.remove();
      app.transportSegments.delete(key);
    }
  }
}

function positionTransportSegment(segment) {
  const start = Number(segment.dataset.start);
  const end = Number(segment.dataset.end);
  if (app.currentTime < start) {
    segment.hidden = true;
    return;
  }

  const startOffset = start - app.currentTime;
  const endOffset = end - app.currentTime;
  const halfSpan = app.visibleSpan / 2;
  const outside = endOffset < -halfSpan || startOffset > halfSpan;
  segment.hidden = outside;
  if (outside) {
    return;
  }

  const left = 50 + (startOffset / app.visibleSpan) * 100;
  const width = Math.max(0.6, ((end - start) / app.visibleSpan) * 100);
  const leftValue = `${left}%`;
  const widthValue = `${width}%`;
  if (segment.style.left !== leftValue) {
    segment.style.left = leftValue;
  }
  if (segment.style.width !== widthValue) {
    segment.style.width = widthValue;
  }
  const isActive = app.currentTime >= start && app.currentTime < end;
  const isCompleted = app.currentTime >= end;
  if (segment.classList.contains("active") !== isActive) {
    segment.classList.toggle("active", isActive);
  }
  if (segment.classList.contains("completed") !== isCompleted) {
    segment.classList.toggle("completed", isCompleted);
  }
}

function refreshTransportSegments(currentTime) {
  app.currentTime = currentTime;
  for (const segment of app.transportSegments.values()) {
    positionTransportSegment(segment);
  }
}

function renderPlan(plan) {
  app.nextOperationStart.clear();
  const machinePlans = new Map();
  for (const operation of plan || []) {
    if (!machinePlans.has(operation.machine_id)) {
      machinePlans.set(operation.machine_id, []);
    }
    machinePlans.get(operation.machine_id).push(operation);
  }
  for (const operations of machinePlans.values()) {
    operations.sort((left, right) => left.start_time - right.start_time);
    for (let index = 0; index < operations.length - 1; index += 1) {
      const operation = operations[index];
      const nextOperation = operations[index + 1];
      app.nextOperationStart.set(
        operationKey(operation.job_id, operation.operation_id),
        nextOperation.start_time,
      );
    }
  }
  syncTransportPlan(plan);

  const planEnd = Math.max(
    0,
    ...((plan || []).map((operation) => operation.end_time)),
  );
  updateHorizon(planEnd);
  refreshBarStates(app.currentTime);
}

function updateHorizon(nextHorizon) {
  if (nextHorizon <= app.horizon) {
    return;
  }
  app.horizon = Math.max(100, Math.ceil(nextHorizon));
  updateVisibleSpan();
  for (const bar of app.bars.values()) {
    positionBar(bar);
  }
  renderAxis();
  renderPlayhead();
}

function updateVisibleSpan() {
  const baseSpan = Math.max(
    60,
    Math.min(150, Math.ceil(app.horizon / 6)),
  );
  app.visibleSpan = baseSpan / (app.displayPercent / 100);
}

function syncDisplaySelect(percent) {
  const value = String(Math.round(percent));
  if (![...elements.displaySelect.options].some((option) => option.value === value)) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = `${value}%`;
    elements.displaySelect.append(option);
  }
  elements.displaySelect.value = value;
}

function applyDisplayPercent(percent) {
  app.displayPercent = Math.max(25, Math.min(300, Number(percent)));
  syncDisplaySelect(app.displayPercent);
  const scale = app.displayPercent / 100;
  const root = document.documentElement;
  root.style.setProperty("--lane-height", `${72 * scale}px`);
  root.style.setProperty("--bar-top", `${9 * scale}px`);
  root.style.setProperty("--bar-height", `${54 * scale}px`);
  root.style.setProperty("--bar-line-height", `${52 * scale}px`);
  root.style.setProperty("--bar-font-size", `${Math.max(8, 11 * scale)}px`);
  root.style.setProperty("--machine-font-size", `${Math.max(8, 11 * scale)}px`);
  root.style.setProperty(
    "--pending-font-size",
    `${Math.max(8, 10 * scale)}px`,
  );
  root.style.setProperty(
    "--pending-chip-width",
    `${78 * scale}px`,
  );
  root.style.setProperty(
    "--pending-chip-height",
    `${40 * scale}px`,
  );
  updateVisibleSpan();
  refreshBarStates(app.currentTime);
  renderAxis();
}

function syncAutoJobSubmission(config = {}) {
  elements.autoJobSubmit.checked = Boolean(config.enabled);
}

function renderAxis() {
  while (elements.timeAxis.children.length < 5) {
    const label = document.createElement("span");
    label.className = "axis-label";
    elements.timeAxis.append(label);
  }
  for (let index = 0; index <= 4; index += 1) {
    const label = elements.timeAxis.children[index];
    label.className = `axis-label${index === 2 ? " current" : ""}`;
    label.style.left = `${index * 25}%`;
    const offset = ((index / 4) - 0.5) * app.visibleSpan;
    const timestamp = Math.round(app.currentTime + offset);
    label.textContent = index === 2 ? `T+${timestamp}` : `${timestamp}`;
  }
}

function renderPlayhead() {
  elements.playhead.style.left = "50%";
}

function refreshBarStates(currentTime) {
  for (const [key, bar] of app.bars.entries()) {
    const start = Number(bar.dataset.start);
    const end = Number(bar.dataset.end);
    let stateClass = "";
    if (end <= currentTime) {
      stateClass = "completed";
    } else if (start <= currentTime) {
      stateClass = "running";
    }
    if (stateClass === "completed" && bar.classList.contains("running")) {
      bar.classList.remove("running");
    } else if (stateClass === "running" && bar.classList.contains("completed")) {
      bar.classList.remove("completed");
    } else if (stateClass === "" ) {
      bar.classList.remove("running", "completed");
    }
    if (stateClass && !bar.classList.contains(stateClass)) {
      bar.classList.add(stateClass);
    }
    positionBar(bar);
  }
  refreshTransportSegments(currentTime);
}

function updateMachineStates(states) {
  const orderedStates = [...(states || [])].sort(
    (left, right) => left.id - right.id,
  );
  for (const state of orderedStates) {
    const lane = ensureLane(state.id);
    const statusText =
      state.status === "busy"
        ? "加工"
        : state.status === "scheduled"
          ? "排队"
          : "空闲";
    lane.status.textContent = `${statusText} · ${state.pending}`;
  }
}

function createPendingChip(operation) {
  const chip = document.createElement("span");
  chip.className = "pending-chip";
  chip.dataset.pendingKey = operationKey(
    operation.job_id,
    operation.operation_id,
  );
  chip.style.setProperty("--chip-hue", jobHue(operation.job_id));
  chip.textContent = `J${operation.job_id}-O${operation.operation_id}`;
  updatePendingChip(chip, operation);
  return chip;
}

function updatePendingChip(chip, operation) {
  chip.title =
    `待加工：作业 ${operation.job_id} / 工序 ${operation.operation_id} / `
    + `计划 ${operation.start_time}-${operation.end_time}`;
}

function replayPendingAnimation(chip, className, delay) {
  chip.classList.remove("pending-shift", "pending-enter");
  void chip.offsetWidth;
  chip.style.animationDelay = `${delay}ms`;
  chip.classList.add(className);
}

function addPendingLeaveAnimation(chip, queue) {
  const queueRect = queue.getBoundingClientRect();
  const chipRect = chip.getBoundingClientRect();
  const ghost = chip.cloneNode(true);
  ghost.classList.remove("pending-shift", "pending-enter");
  ghost.classList.add("pending-leaving");
  ghost.style.left = `${chipRect.left - queueRect.left}px`;
  ghost.style.top = `${chipRect.top - queueRect.top}px`;
  ghost.style.width = `${chipRect.width}px`;
  ghost.style.height = `${chipRect.height}px`;
  queue.append(ghost);
  window.setTimeout(() => ghost.remove(), 340);
}

function renderPendingQueues(plan, currentTime) {
  const queues = new Map();
  for (const operation of plan || []) {
    if (operation.start_time <= currentTime) {
      continue;
    }
    if (!queues.has(operation.machine_id)) {
      queues.set(operation.machine_id, []);
    }
    queues.get(operation.machine_id).push(operation);
  }

  for (const [machineId, lane] of app.lanes.entries()) {
    const pending = (queues.get(machineId) || []).sort(
      (left, right) => left.start_time - right.start_time,
    );
    const railWidth = lane.pendingQueue.clientWidth || 420;
    const signature = pending
      .map((operation) => {
        const key = operationKey(
          operation.job_id,
          operation.operation_id,
        );
        return [
          key,
          operation.start_time,
          operation.end_time,
          operation.transport_start,
          operation.transport_end,
        ].join(":");
      })
      .concat(`@${app.displayPercent}@${railWidth}`)
      .join("|");
    if (app.pendingSignatures.get(machineId) === signature) {
      continue;
    }

    const chipWidth = 78 * (app.displayPercent / 100) + 6;
    const visibleCount = Math.max(
      1,
      Math.min(8, Math.floor((railWidth - 24) / chipWidth)),
    );
    const visibleOperations = pending.slice(0, visibleCount);
    const visibleKeys = visibleOperations.map((operation) =>
      operationKey(operation.job_id, operation.operation_id)
    );
    const desiredKeys = new Set(visibleKeys);
    const oldChips = [
      ...lane.pendingQueue.querySelectorAll(
        ".pending-chip:not(.pending-leaving)",
      ),
    ];
    const oldIndexes = new Map(
      oldChips.map((chip, index) => [chip.dataset.pendingKey, index]),
    );
    const chipByKey = new Map(
      oldChips.map((chip) => [chip.dataset.pendingKey, chip]),
    );

    lane.pendingQueue
      .querySelectorAll(".pending-more, .pending-empty")
      .forEach((element) => element.remove());

    for (const chip of oldChips) {
      if (!desiredKeys.has(chip.dataset.pendingKey)) {
        addPendingLeaveAnimation(chip, lane.pendingQueue);
        chip.remove();
      }
    }

    visibleOperations.forEach((operation, index) => {
      const key = visibleKeys[index];
      let chip = chipByKey.get(key);
      const isNewChip = chip === undefined;
      if (isNewChip) {
        chip = createPendingChip(operation);
      } else {
        updatePendingChip(chip, operation);
      }
      lane.pendingQueue.append(chip);

      if (isNewChip) {
        replayPendingAnimation(chip, "pending-enter", index * 55);
      } else {
        const previousIndex = oldIndexes.get(key);
        if (previousIndex > index) {
          replayPendingAnimation(
            chip,
            "pending-shift",
            index * 45,
          );
        }
      }
    });

    if (visibleOperations.length === 0) {
      const empty = document.createElement("span");
      empty.className = "pending-empty";
      empty.textContent = "—";
      lane.pendingQueue.append(empty);
    } else if (pending.length > visibleCount) {
      const more = document.createElement("span");
      more.className = "pending-more";
      more.textContent = `+${pending.length - visibleCount}`;
      lane.pendingQueue.append(more);
    }
    app.pendingSignatures.set(machineId, signature);
  }
}

function eventDescription(event) {
  if (event.job_id !== undefined && event.operation_id !== undefined) {
    return `作业 ${event.job_id} / 工序 ${event.operation_id} / M${event.machine_id ?? "-"}`;
  }
  if (event.machine_id !== undefined) {
    return `机器 M${event.machine_id}`;
  }
  return "";
}

function addEvent(event) {
  const empty = elements.eventList.querySelector(".empty-state");
  if (empty) {
    empty.remove();
  }

  const row = document.createElement("div");
  row.className = "event-row";
  const typeLabel = EVENT_TEXT[event.type] || event.type;
  row.innerHTML = `
    <span class="event-time">T+${formatTime(event.timestamp)}</span>
    <i class="event-dot"></i>
    <div class="event-copy">
      <strong>${escapeHtml(typeLabel)}</strong>
      <span>${escapeHtml(eventDescription(event))}</span>
    </div>
  `;
  elements.eventList.prepend(row);
  while (elements.eventList.children.length > 320) {
    elements.eventList.lastElementChild.remove();
  }

  app.eventCount += 1;
  elements.eventCount.textContent = app.eventCount;
}

function handleOperationEvent(event) {
  if (
    event.type !== "OperationStartEvent"
    && event.type !== "OperationFinishEvent"
  ) {
    return;
  }

  const key = operationKey(event.job_id, event.operation_id);
  let bar = app.bars.get(key);
  if (!bar) {
    bar = ensureBar({
      job_id: event.job_id,
      operation_id: event.operation_id,
      machine_id: event.machine_id,
      start_time: event.timestamp,
      end_time: event.timestamp + (event.processing_time || 0),
    });
  }

  if (event.type === "OperationStartEvent") {
    bar.dataset.start = event.timestamp;
    bar.dataset.end = event.timestamp + (event.processing_time || 0);
    bar.classList.remove("entering-current");
    void bar.offsetWidth;
    bar.classList.add("entering-current");
    window.setTimeout(
      () => bar.classList.remove("entering-current"),
      540,
    );
  } else {
    bar.dataset.end = event.timestamp;
  }
}

function setStatus(status) {
  app.status = status;
  elements.connectionStatus.className = `status-pill ${status}`;
  elements.connectionStatus.textContent = STATUS_TEXT[status] || status;
  elements.startButton.disabled =
    !app.datasetsReady
    || status === "running"
    || status === "preparing"
    || status === "reoptimizing";
  elements.datasetSelect.disabled =
    status === "running"
    || status === "preparing"
    || status === "reoptimizing";
  elements.reoptimizerSelect.disabled = status !== "running";
  elements.reoptimizeButton.disabled = status !== "running";
  elements.manualJobInsertButton.disabled = status !== "running";
  updateReoptimizeButtonText();
  elements.startButton.textContent =
    status === "finished" ? "再次启动" : "启动仿真";
}

const REOPTIMIZERS = {
  mofjsp: {
    endpoint: "/api/reoptimize",
    label: "DRL",
    buttonLabel: "DRL 重调度",
    busyLabel: "DRL 重调度中...",
    payload: { num_samples: 1, seed: 0 },
  },
  hls: {
    endpoint: "/api/hls-reoptimize",
    label: "HLS",
    buttonLabel: "HLS 重调度",
    busyLabel: "HLS 重调度中...",
    payload: { seed: 0 },
  },
};

function selectedReoptimizer() {
  return REOPTIMIZERS[elements.reoptimizerSelect.value]
    || REOPTIMIZERS.mofjsp;
}

function updateReoptimizeButtonText() {
  if (app.status === "reoptimizing") {
    return;
  }
  elements.reoptimizeButton.textContent =
    selectedReoptimizer().buttonLabel;
}

async function reoptimizeWithSelectedMethod() {
  const optimizer = selectedReoptimizer();
  elements.reoptimizeButton.disabled = true;
  elements.reoptimizerSelect.disabled = true;
  elements.reoptimizeButton.textContent = optimizer.busyLabel;
  try {
    const response = await fetch(optimizer.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(optimizer.payload),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent =
      `${optimizer.label}重调度失败：${error.message}`;
  } finally {
    updateReoptimizeButtonText();
    elements.reoptimizeButton.disabled = app.status !== "running";
    elements.reoptimizerSelect.disabled = app.status !== "running";
  }
}

function syncSpeedSelect(speed) {
  const value = String(Number(speed));
  if (![...elements.speedSelect.options].some((option) => option.value === value)) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = `${value}x`;
    elements.speedSelect.append(option);
  }
  elements.speedSelect.value = value;
}

function applySnapshot(snapshot) {
  if (app.generation !== null && app.generation !== snapshot.generation) {
    resetView();
  }
  app.generation = snapshot.generation;
  if (snapshot.selected_dataset?.id) {
    elements.datasetSelect.value = snapshot.selected_dataset.id;
  }
  app.speed = snapshot.speed;
  const serverTime = Number(snapshot.current_time || 0);
  if (
    snapshot.status === "running"
    || snapshot.status === "reoptimizing"
  ) {
    app.currentTime = Math.max(app.currentTime, serverTime);
  } else {
    app.currentTime = serverTime;
  }
  app.serverTime = serverTime;
  app.lastServerTime = app.currentTime;
  app.lastSyncAt = performance.now();
  syncSpeedSelect(snapshot.speed);
  applyDisplayPercent(snapshot.display_percent || 100);

  updateHorizon(Number(snapshot.horizon || 100));
  renderPlan(snapshot.plan);
  renderAxis();
  updateMachineStates(snapshot.machine_states);

  for (const event of snapshot.events) {
    handleOperationEvent(event);
    addEvent(event);
  }
  app.after = snapshot.next_event_index;

  elements.currentTime.textContent = formatTime(app.currentTime);
  elements.clockReadout.textContent = `T+${String(Math.round(app.currentTime)).padStart(4, "0")}`;
  elements.makespan.textContent = snapshot.makespan || "--";
  elements.finishedJobs.textContent = `${snapshot.finished_jobs} / ${snapshot.total_jobs}`;
  elements.totalEnergy.textContent =
    snapshot.objectives?.energy === undefined
      ? "--"
      : String(Math.round(Number(snapshot.objectives.energy)));
  elements.deliveryPenalty.textContent =
    snapshot.objectives?.penalty === undefined
      ? "--"
      : String(Math.round(Number(snapshot.objectives.penalty)));
  setStatus(snapshot.status);
  refreshBarStates(app.currentTime);
  renderPendingQueues(snapshot.plan, app.serverTime);
  renderPlayhead();
  syncAutoJobSubmission(snapshot.auto_job_submission);

  elements.errorBanner.classList.toggle("hidden", !snapshot.error);
  if (snapshot.error) {
    elements.errorBanner.textContent = snapshot.error;
  }
}

async function poll() {
  try {
    const response = await fetch(`/api/state?after=${app.after}`, {
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    applySnapshot(await response.json());
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent = `无法连接仿真服务：${error.message}`;
  } finally {
    if (app.status !== "finished" && app.status !== "failed") {
      pollTimer = window.setTimeout(poll, 200);
    }
  }
}

async function startSimulation() {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer);
  }
  resetView();
  app.datasetsReady = true;
  elements.startButton.disabled = true;
  const datasetId = elements.datasetSelect.value;
  if (!datasetId) {
    elements.startButton.disabled = false;
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent = "请先选择数据源。";
    return;
  }
  try {
    const response = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_id: datasetId }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const result = await response.json();
    setStatus(result.status);
    pollTimer = window.setTimeout(poll, 100);
  } catch (error) {
    elements.startButton.disabled = false;
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent = `启动仿真失败：${error.message}`;
  }
}

async function loadDatasets() {
  try {
    const response = await fetch("/api/datasets", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const result = await response.json();
    elements.datasetSelect.replaceChildren();
    for (const dataset of result.datasets) {
      const option = document.createElement("option");
      option.value = dataset.id;
      option.textContent = dataset.label;
      option.title = dataset.id;
      option.selected = dataset.id === result.default_dataset;
      elements.datasetSelect.append(option);
    }
    app.datasetsReady = true;
    setStatus(app.status);
    poll();
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent = `读取数据源失败：${error.message}`;
  }
}

async function changeSpeed() {
  const speed = Number(elements.speedSelect.value);
  try {
    const response = await fetch("/api/speed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ speed }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    app.speed = speed;
    app.lastServerTime = app.currentTime;
    app.lastSyncAt = performance.now();
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent = `调整倍速失败：${error.message}`;
  }
}

async function changeAutoJobSubmission() {
  const enabled = elements.autoJobSubmit.checked;
  try {
    const response = await fetch("/api/auto-job-submission", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    syncAutoJobSubmission(result.auto_job_submission);
  } catch (error) {
    elements.autoJobSubmit.checked = !enabled;
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent =
      `设置自动插单失败：${error.message}`;
  }
}

async function insertJobsManually() {
  elements.manualJobInsertButton.disabled = true;
  elements.manualJobInsertButton.textContent = "插单中...";
  try {
    const response = await fetch("/api/jobs/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        seed: Math.floor(Math.random() * 1_000_000_000),
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent =
      `手动插单失败：${error.message}`;
  } finally {
    elements.manualJobInsertButton.textContent = "手动插单";
    elements.manualJobInsertButton.disabled = app.status !== "running";
  }
}

function animateTimeline(now) {
  if (app.status === "running" && now - app.lastFrameRenderAt >= 16) {
    const estimatedTime =
      app.lastServerTime
      + ((now - app.lastSyncAt) / 1000) * app.speed;
    if (estimatedTime > app.currentTime) {
      app.currentTime = estimatedTime;
      elements.currentTime.textContent = formatTime(app.currentTime);
      elements.clockReadout.textContent =
        `T+${String(Math.round(app.currentTime)).padStart(4, "0")}`;
      refreshBarStates(app.currentTime);
      if (now - app.lastAxisRenderAt >= 100) {
        renderAxis();
        app.lastAxisRenderAt = now;
      }
    }
    app.lastFrameRenderAt = now;
  }
  window.requestAnimationFrame(animateTimeline);
}

async function changeDisplayPercent() {
  const displayPercent = Number(elements.displaySelect.value);
  applyDisplayPercent(displayPercent);
  try {
    const response = await fetch("/api/display-percent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_percent: displayPercent }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    elements.errorBanner.classList.remove("hidden");
    elements.errorBanner.textContent = `调整显示比例失败：${error.message}`;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

renderAxis();
setStatus("idle");
elements.startButton.addEventListener("click", startSimulation);
elements.autoJobSubmit.addEventListener(
  "change",
  changeAutoJobSubmission,
);
elements.manualJobInsertButton.addEventListener(
  "click",
  insertJobsManually,
);
elements.reoptimizeButton.addEventListener(
  "click",
  reoptimizeWithSelectedMethod,
);
elements.reoptimizerSelect.addEventListener(
  "change",
  updateReoptimizeButtonText,
);
elements.speedSelect.addEventListener("change", changeSpeed);
elements.displaySelect.addEventListener("change", changeDisplayPercent);
elements.timelineBody.addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown" || event.key === "PageDown") {
    event.preventDefault();
    elements.timelineBody.scrollBy({
      top: elements.timelineBody.clientHeight * 0.8,
      behavior: "smooth",
    });
  } else if (event.key === "ArrowUp" || event.key === "PageUp") {
    event.preventDefault();
    elements.timelineBody.scrollBy({
      top: -elements.timelineBody.clientHeight * 0.8,
      behavior: "smooth",
    });
  }
});
enableTimelineWheelScroll();
window.requestAnimationFrame(animateTimeline);
loadDatasets();
