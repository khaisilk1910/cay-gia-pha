const MODULE_URL = new URL(import.meta.url);
const RESOURCE_VERSION = MODULE_URL.searchParams.get("v") || "";

function withResourceVersion(path) {
  if (!RESOURCE_VERSION) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}v=${encodeURIComponent(RESOURCE_VERSION)}`;
}

const TREE_CACHE_MAX_AGE = 6 * 24 * 60 * 60 * 1000;
const FAMILY_TREE_CACHE = new Map();
let CARD_STYLES_CACHE = null;

const DEFAULT_CONFIG = {
  title: "Gia Phả Cụ Tiến Tiệp",
  subtitle: "Theo dấu các thế hệ trong gia đình qua năm tháng.",
  title_font: "noto-serif",
  content_font: "noto-sans",
  title_font_size: 46,
  subtitle_font_size: 14,
  background_color: "#fbfaf6",
  text_color: "#171512",
  muted_text_color: "#655f55",
  line_color: "#aaa493",
  border_color: "#d9d3c5",
  male_color: "#557d96",
  female_color: "#a97887",
  other_color: "#7d7294",
  decoration_color: "#d8d2c1",
  border_radius: 18,
  avatar_size: 70,
  node_width: 156,
  horizontal_spacing: 34,
  vertical_spacing: 84,
  show_summary: false,
  show_dates: true,
  show_age: false,
  show_details: true,
  show_decorations: true,
  deceased_grayscale: true,
  show_zoom: true,
  initial_zoom: 50,
  limit_initial_generations: false,
  initial_generation_limit: 3,
};

const GENDER_LABEL = { male: "Nam", female: "Nữ", other: "Khác" };

const DEFAULT_AVATAR_URLS = {
  male: withResourceVersion("/cay_gia_pha_static/avatar-male.svg"),
  female: withResourceVersion("/cay_gia_pha_static/avatar-female.svg"),
  other: withResourceVersion("/cay_gia_pha_static/avatar-placeholder.svg"),
};

const FONT_OPTIONS = [
  { value: "noto-serif", label: "Noto Serif · trang trọng, hỗ trợ tiếng Việt", stack: '"Noto Serif", "DejaVu Serif", "Liberation Serif", serif' },
  { value: "noto-sans", label: "Noto Sans · rõ ràng, hỗ trợ tiếng Việt", stack: '"Noto Sans", "DejaVu Sans", "Liberation Sans", Arial, sans-serif' },
  { value: "palatino", label: "Palatino", stack: '"Palatino Linotype", "Book Antiqua", "Noto Serif", "DejaVu Serif", serif' },
  { value: "times", label: "Times New Roman", stack: '"Times New Roman", "Noto Serif", "DejaVu Serif", serif' },
  { value: "segoe", label: "Segoe UI", stack: '"Segoe UI", Roboto, "Noto Sans", "DejaVu Sans", sans-serif' },
  { value: "arial", label: "Arial", stack: 'Arial, "Noto Sans", "DejaVu Sans", sans-serif' },
  { value: "tahoma", label: "Tahoma", stack: 'Tahoma, "Noto Sans", "DejaVu Sans", sans-serif' },
  { value: "verdana", label: "Verdana", stack: 'Verdana, "Noto Sans", "DejaVu Sans", sans-serif' },
  { value: "trebuchet", label: "Trebuchet MS", stack: '"Trebuchet MS", "Noto Sans", "DejaVu Sans", sans-serif' },
  { value: "system", label: "Phông hệ thống", stack: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", sans-serif' },
];

class CayGiaPhaCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = { ...DEFAULT_CONFIG };
    this._tree = null;
    this._loading = false;
    this._error = null;
    this._requestKey = null;
    this._loadingKey = null;
    this._treeLoadedAt = 0;
    this._summaryEntityId = null;
    this._selectedPersonId = null;
    this._zoom = DEFAULT_CONFIG.initial_zoom / 100;
    this._needsInitialCenter = true;
    this._pendingViewport = null;
    this._fitTreeAfterRender = false;
    this._collapsedFamilies = new Set();
    this._initialGenerationApplied = false;
    this._suppressPersonClickUntil = 0;
    this._wheelZoomFrame = null;
    this._wheelZoomDelta = 0;
    this._wheelZoomPoint = null;
    this._imageRefreshTimer = null;
    this._resizeTimer = null;
    this._observedWidth = 0;
    this._normalizedTree = null;
    this._normalizedPeople = [];
    this._completeMaps = null;
    this._collapseFamiliesCache = null;
    this._layoutCache = null;
    this._layoutDirty = true;
    this._waitingForEntityRendered = false;

    this.shadowRoot.addEventListener("click", (event) => this._handleShadowClick(event));
    this.shadowRoot.addEventListener("keydown", (event) => this._handleShadowKeydown(event));
    this.shadowRoot.addEventListener("error", (event) => this._handleImageError(event), true);

    this._resizeObserver = new ResizeObserver((entries) => {
      const width = Math.round(entries[0]?.contentRect?.width || this.clientWidth || 0);
      if (!width || Math.abs(width - this._observedWidth) < 2) return;
      this._observedWidth = width;
      clearTimeout(this._resizeTimer);
      this._resizeTimer = setTimeout(() => {
        this._layoutDirty = true;
        this._render();
      }, 80);
    });
  }

  connectedCallback() {
    this._resizeObserver.observe(this);
    this._render();
    if (this._tree && this._requestKey) {
      this._scheduleImageRefresh(this._requestKey, this._tree);
    }
    if (this._hass) this._maybeLoadTree();
  }

  disconnectedCallback() {
    this._resizeObserver.disconnect();
    clearTimeout(this._resizeTimer);
    if (this._wheelZoomFrame) cancelAnimationFrame(this._wheelZoomFrame);
    if (this._imageRefreshTimer) clearTimeout(this._imageRefreshTimer);
  }

  static getStubConfig() {
    return {};
  }

  static async getConfigElement() {
    return document.createElement("cay-gia-pha-card-editor");
  }

  getCardSize() {
    return 10;
  }

  getGridOptions() {
    return {
      columns: 12,
      min_columns: 6,
      min_rows: 5,
    };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("Cấu hình thẻ Cây Gia Phả không hợp lệ");
    }
    const nextConfig = { ...DEFAULT_CONFIG, ...config };
    if (sameCardConfig(this._config, nextConfig) && this.shadowRoot?.childElementCount) return;

    this._config = nextConfig;
    this._error = null;
    this._zoom = this._initialZoom();
    this._needsInitialCenter = true;
    this._collapsedFamilies.clear();
    this._initialGenerationApplied = false;
    this._layoutDirty = true;
    this._render();
    this._maybeLoadTree();
  }

  set hass(hass) {
    this._hass = hass;
    this._maybeLoadTree(this._findSummaryEntity());
  }

  get hass() {
    return this._hass;
  }

  _findSummaryEntity() {
    if (!this._hass) return null;
    if (this._summaryEntityId) {
      const cached = this._hass.states[this._summaryEntityId];
      if (
        cached?.attributes?.integration === "cay_gia_pha" &&
        cached.attributes?.entry_id &&
        !cached.attributes?.person_id
      ) {
        return cached;
      }
      this._summaryEntityId = null;
    }

    for (const [entityId, state] of Object.entries(this._hass.states)) {
      if (
        state.attributes?.integration === "cay_gia_pha" &&
        state.attributes?.entry_id &&
        !state.attributes?.person_id
      ) {
        this._summaryEntityId = entityId;
        return state;
      }
    }
    return null;
  }

  async _maybeLoadTree(entity = this._findSummaryEntity()) {
    if (!this._hass || !entity) {
      if (!this._tree && !this._loadingKey && !this._waitingForEntityRendered) {
        this._waitingForEntityRendered = true;
        this._render();
      }
      return;
    }
    this._waitingForEntityRendered = false;

    const entryId = entity.attributes.entry_id;
    const revision = entity.attributes.revision ?? 0;
    if (!entryId) {
      this._error = "Không tìm thấy entry_id của tích hợp Cây Gia Phả.";
      this._render();
      return;
    }

    const requestKey = `${entryId}:${revision}`;
    if (this._loadingKey || this._requestKey === requestKey) return;

    this._loadingKey = requestKey;
    this._loading = !this._tree;
    this._error = null;
    if (this._loading) this._render();
    try {
      const tree = await loadFamilyTree(this._hass, entryId, revision);
      const currentEntity = this._findSummaryEntity();
      const currentKey = currentEntity
        ? `${currentEntity.attributes.entry_id}:${currentEntity.attributes.revision ?? 0}`
        : null;
      if (currentKey !== requestKey) return;

      this._tree = tree;
      this._requestKey = requestKey;
      this._treeLoadedAt = Date.now();
      this._invalidateTreeCaches();
      this._scheduleImageRefresh(requestKey, tree);
      if (
        this._selectedPersonId &&
        !tree.people.some((person) => String(person.person_id) === this._selectedPersonId)
      ) {
        this._selectedPersonId = null;
      }
    } catch (error) {
      this._error = error?.message || String(error);
    } finally {
      if (this._loadingKey === requestKey) this._loadingKey = null;
      this._loading = false;
      const currentEntity = this._findSummaryEntity();
      const currentKey = currentEntity
        ? `${currentEntity.attributes.entry_id}:${currentEntity.attributes.revision ?? 0}`
        : null;
      if (this._requestKey === requestKey || this._error) this._render();
      if (currentKey && currentKey !== this._requestKey) this._maybeLoadTree(currentEntity);
    }
  }

  _render() {
    if (!this.shadowRoot) return;
    const previousScroller = this.shadowRoot.querySelector(".tree-scroll");
    const previousScroll = previousScroller
      ? { left: previousScroller.scrollLeft, top: previousScroller.scrollTop }
      : null;
    const config = this._config;
    const tree = this._tree;
    const layout = tree ? this._getLayout() : null;
    const title = config.title || tree?.title || "Cây Gia Phả";

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card class="family-card">
        <div class="paper-grain" aria-hidden="true"></div>
        <header class="family-header">
          ${config.show_decorations ? this._cornerOrnament("left") : ""}
          <div class="family-heading">
            <h1>${escapeHtml(title)}</h1>
            ${config.subtitle ? `<p>${escapeHtml(config.subtitle)}</p>` : ""}
          </div>
          ${config.show_decorations ? this._cornerOrnament("right") : ""}
          <div class="header-actions">
            ${config.show_zoom ? this._zoomControls() : ""}
            ${tree ? this._pdfExportButton() : ""}
          </div>
        </header>
        ${config.show_summary && tree ? this._summary(tree.stats || {}) : ""}
        <div class="family-content">${this._content(layout)}</div>
        <div class="print-icon-cache" aria-hidden="true">
          <ha-icon icon="mdi:account-group-outline"></ha-icon>
          <ha-icon icon="mdi:gender-male"></ha-icon>
          <ha-icon icon="mdi:gender-female"></ha-icon>
          <ha-icon icon="mdi:heart-pulse"></ha-icon>
          <ha-icon icon="mdi:candle"></ha-icon>
          <ha-icon icon="mdi:layers-triple-outline"></ha-icon>
        </div>
      </ha-card>
    `;

    const card = this.shadowRoot.querySelector(".family-card");
    if (card) {
      card.style.setProperty("--family-bg", safeColor(config.background_color, DEFAULT_CONFIG.background_color));
      card.style.setProperty("--family-text", safeColor(config.text_color, DEFAULT_CONFIG.text_color));
      card.style.setProperty("--family-muted", safeColor(config.muted_text_color, DEFAULT_CONFIG.muted_text_color));
      card.style.setProperty("--family-line", safeColor(config.line_color, DEFAULT_CONFIG.line_color));
      card.style.setProperty("--family-border", safeColor(config.border_color, DEFAULT_CONFIG.border_color));
      card.style.setProperty("--family-male", safeColor(config.male_color, DEFAULT_CONFIG.male_color));
      card.style.setProperty("--family-female", safeColor(config.female_color, DEFAULT_CONFIG.female_color));
      card.style.setProperty("--family-other", safeColor(config.other_color, DEFAULT_CONFIG.other_color));
      card.style.setProperty("--family-decoration", safeColor(config.decoration_color, DEFAULT_CONFIG.decoration_color));
      card.style.setProperty("--family-radius", `${clampNumber(config.border_radius, 0, 48, 18)}px`);
      card.style.setProperty("--family-title-font", fontStack(config.title_font, "noto-serif"));
      card.style.setProperty("--family-content-font", fontStack(config.content_font, "noto-sans"));
      card.style.setProperty("--family-title-size", `${clampNumber(config.title_font_size, 20, 80, 46)}px`);
      card.style.setProperty("--family-subtitle-size", `${clampNumber(config.subtitle_font_size, 10, 32, 14)}px`);
      if (config.background_image) {
        card.style.setProperty(
          "--family-bg-image",
          `linear-gradient(rgba(251,250,246,.82), rgba(251,250,246,.88)), url("${cssUrl(config.background_image)}")`
        );
      } else {
        card.style.removeProperty("--family-bg-image");
      }
    }

    this._renderDetailPanel();

    const scroller = this.shadowRoot.querySelector(".tree-scroll");
    if (scroller) {
      const pendingViewport = this._pendingViewport;
      this._pendingViewport = null;
      this._bindTreeNavigation(scroller);
      requestAnimationFrame(() => {
        if (!scroller.isConnected) return;
        const stage = scroller.querySelector(".scaled-stage");
        if (this._fitTreeAfterRender && layout) {
          this._fitTreeAfterRender = false;
          this._fitTreeToViewport(scroller, layout);
          return;
        }
        if (pendingViewport?.mode === "focal" && stage) {
          this._needsInitialCenter = false;
          scroller.scrollLeft = Math.max(
            0,
            stage.offsetLeft + pendingViewport.treeX * this._zoom - pendingViewport.viewportX,
          );
          scroller.scrollTop = Math.max(
            0,
            stage.offsetTop + pendingViewport.treeY * this._zoom - pendingViewport.viewportY,
          );
        } else if (pendingViewport?.mode === "center") {
          this._needsInitialCenter = false;
          scroller.scrollLeft = Math.max(0, (scroller.scrollWidth - scroller.clientWidth) / 2);
          scroller.scrollTop = Math.max(0, pendingViewport.top || 0);
        } else if (this._needsInitialCenter) {
          scroller.scrollLeft = Math.max(0, (scroller.scrollWidth - scroller.clientWidth) / 2);
          scroller.scrollTop = 0;
          this._needsInitialCenter = false;
        } else if (previousScroll) {
          scroller.scrollLeft = previousScroll.left;
          scroller.scrollTop = previousScroll.top;
        }
      });
    }

  }

  _handleShadowClick(event) {
    const target = event.target;
    if (!(target instanceof Element)) return;

    const closeButton = target.closest(".detail-close");
    if (closeButton) {
      this._setSelectedPerson(null);
      return;
    }

    if (target.classList.contains("detail-backdrop")) {
      this._setSelectedPerson(null);
      return;
    }

    const branchButton = target.closest(".branch-toggle");
    if (branchButton) {
      event.preventDefault();
      event.stopPropagation();
      const familyKey = branchButton.dataset.familyKey;
      if (!familyKey) return;
      if (this._collapsedFamilies.has(familyKey)) this._collapsedFamilies.delete(familyKey);
      else this._collapsedFamilies.add(familyKey);
      this._layoutDirty = true;
      this._render();
      return;
    }

    const exportButton = target.closest("[data-export-pdf]");
    if (exportButton) {
      event.preventDefault();
      this._exportTreeToPdf();
      return;
    }

    const fitTreeButton = target.closest("[data-fit-tree]");
    if (fitTreeButton) {
      event.preventDefault();
      event.stopPropagation();
      this._expandAllAndFit();
      return;
    }

    const zoomButton = target.closest("[data-zoom]");
    if (zoomButton) {
      const action = zoomButton.dataset.zoom;
      const currentScroller = this.shadowRoot.querySelector(".tree-scroll");
      if (action === "in") this._setZoom(this._zoom + 0.1, currentScroller);
      if (action === "out") this._setZoom(this._zoom - 0.1, currentScroller);
      if (action === "reset") this._setZoom(this._initialZoom(), currentScroller, null, null, true);
      return;
    }

    const node = target.closest(".person-node");
    if (!node || Date.now() < this._suppressPersonClickUntil) return;
    this._setSelectedPerson(node.dataset.personId);
  }

  _handleShadowKeydown(event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    const target = event.target;
    if (!(target instanceof Element)) return;
    const node = target.closest(".person-node");
    if (!node || Date.now() < this._suppressPersonClickUntil) return;
    event.preventDefault();
    this._setSelectedPerson(node.dataset.personId);
  }

  _setSelectedPerson(personId) {
    this._selectedPersonId = personId ? String(personId) : null;
    this._renderDetailPanel();
  }

  _renderDetailPanel() {
    const card = this.shadowRoot?.querySelector(".family-card");
    if (!card) return;
    card.querySelector(":scope > .detail-backdrop")?.remove();
    if (!this._selectedPersonId || !this._config?.show_details || !this._tree) return;

    const people = this._prepareTreeData();
    const person = this._completeMaps?.byId.get(this._selectedPersonId);
    if (!person) {
      this._selectedPersonId = null;
      return;
    }
    card.insertAdjacentHTML(
      "beforeend",
      this._detailPanel(person, people, this._completeMaps),
    );
  }

  _handleImageError(event) {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || !image.matches("img[data-fallback]")) return;
    const fallbackSrc = image.dataset.fallbackSrc;
    if (fallbackSrc && image.getAttribute("src") !== fallbackSrc) {
      image.src = fallbackSrc;
      delete image.dataset.fallbackSrc;
      return;
    }
    const fallback = document.createElement("div");
    fallback.className = image.dataset.fallbackClass || "avatar-placeholder";
    fallback.textContent = image.dataset.fallback || "?";
    image.replaceWith(fallback);
  }

  _bindTreeNavigation(scroller) {
    let pan = null;
    const endPan = (event) => {
      if (!pan || event.pointerId !== pan.pointerId) return;
      if (pan.dragged) this._suppressPersonClickUntil = Date.now() + 350;
      scroller.classList.remove("is-panning");
      if (scroller.hasPointerCapture?.(event.pointerId)) {
        scroller.releasePointerCapture(event.pointerId);
      }
      pan = null;
    };

    scroller.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      if (event.target?.closest?.("button, a, input, select, textarea")) return;
      pan = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        scrollLeft: scroller.scrollLeft,
        scrollTop: scroller.scrollTop,
        dragged: false,
      };
    });

    scroller.addEventListener("pointermove", (event) => {
      if (!pan || event.pointerId !== pan.pointerId) return;
      const deltaX = event.clientX - pan.startX;
      const deltaY = event.clientY - pan.startY;
      if (!pan.dragged && Math.hypot(deltaX, deltaY) < 5) return;
      if (!pan.dragged) {
        pan.dragged = true;
        scroller.classList.add("is-panning");
        scroller.setPointerCapture?.(event.pointerId);
      }
      event.preventDefault();
      scroller.scrollLeft = pan.scrollLeft - deltaX;
      scroller.scrollTop = pan.scrollTop - deltaY;
    });

    scroller.addEventListener("pointerup", endPan);
    scroller.addEventListener("pointercancel", endPan);
    scroller.addEventListener("lostpointercapture", endPan);

    scroller.addEventListener("wheel", (event) => {
      event.preventDefault();
      this._wheelZoomDelta += event.deltaY;
      this._wheelZoomPoint = {
        scroller,
        clientX: event.clientX,
        clientY: event.clientY,
      };
      if (this._wheelZoomFrame) return;
      this._wheelZoomFrame = requestAnimationFrame(() => {
        this._wheelZoomFrame = null;
        const delta = this._wheelZoomDelta;
        const point = this._wheelZoomPoint;
        this._wheelZoomDelta = 0;
        this._wheelZoomPoint = null;
        if (!point || !delta) return;
        const step = Math.min(0.12, Math.max(0.02, Math.abs(delta) / 1000));
        const nextZoom = this._zoom + (delta < 0 ? step : -step);
        this._setZoom(nextZoom, point.scroller, point.clientX, point.clientY);
      });
    }, { passive: false });
  }

  _expandAllAndFit() {
    // Mark the automatic generation limit as already handled so opening every
    // branch is not immediately undone by _applyInitialGenerationCollapse().
    this._initialGenerationApplied = true;
    this._collapsedFamilies.clear();
    this._layoutDirty = true;
    this._fitTreeAfterRender = true;
    this._needsInitialCenter = false;
    this._pendingViewport = null;
    this._render();
  }

  _fitTreeToViewport(scroller, layout) {
    if (!scroller?.isConnected || !layout?.width || !layout?.height) return;

    const rect = scroller.getBoundingClientRect();
    const viewportHeight = Math.max(320, window.visualViewport?.height || window.innerHeight || 0);
    const availableWidth = Math.max(160, scroller.clientWidth - 24);
    const availableHeight = Math.max(220, viewportHeight - Math.max(0, rect.top) - 24);
    const widthZoom = availableWidth / layout.width;
    const heightZoom = availableHeight / layout.height;
    const fitZoom = clampNumber(Math.min(widthZoom, heightZoom, 1), 0.01, 1.6, this._initialZoom());

    this._setZoom(fitZoom, scroller, null, null, true);
    requestAnimationFrame(() => {
      if (!scroller.isConnected) return;
      scroller.scrollLeft = Math.max(0, (scroller.scrollWidth - scroller.clientWidth) / 2);
      scroller.scrollTop = Math.max(0, (scroller.scrollHeight - scroller.clientHeight) / 2);
    });
  }

  _initialZoom() {
    return clampNumber(this._config?.initial_zoom, 50, 160, 50) / 100;
  }

  _setZoom(nextZoom, scroller = null, clientX = null, clientY = null, center = false) {
    const zoom = clampNumber(nextZoom, 0.01, 1.6, this._initialZoom());
    const activeScroller = scroller || this.shadowRoot.querySelector(".tree-scroll");
    if (Math.abs(zoom - this._zoom) < 0.001) {
      if (center && activeScroller) {
        requestAnimationFrame(() => {
          if (!activeScroller.isConnected) return;
          activeScroller.scrollLeft = Math.max(
            0,
            (activeScroller.scrollWidth - activeScroller.clientWidth) / 2,
          );
          activeScroller.scrollTop = 0;
        });
      }
      return;
    }

    let viewport = null;
    if (center) {
      viewport = { mode: "center", top: 0 };
    } else if (activeScroller) {
      const stage = activeScroller.querySelector(".scaled-stage");
      const scrollerRect = activeScroller.getBoundingClientRect();
      const stageRect = stage?.getBoundingClientRect();
      const pointerX = Number.isFinite(clientX) ? clientX : scrollerRect.left + activeScroller.clientWidth / 2;
      const pointerY = Number.isFinite(clientY) ? clientY : scrollerRect.top + activeScroller.clientHeight / 2;
      if (stageRect) {
        viewport = {
          mode: "focal",
          treeX: (pointerX - stageRect.left) / this._zoom,
          treeY: (pointerY - stageRect.top) / this._zoom,
          viewportX: pointerX - scrollerRect.left,
          viewportY: pointerY - scrollerRect.top,
        };
      }
    }

    this._zoom = zoom;
    const layout = this._layoutCache;
    const stage = activeScroller?.querySelector(".scaled-stage");
    const canvas = activeScroller?.querySelector(".tree-canvas");
    if (!layout || !stage || !canvas) {
      this._pendingViewport = viewport;
      this._render();
      return;
    }

    stage.style.width = `${Math.ceil(layout.width * zoom)}px`;
    stage.style.height = `${Math.ceil(layout.height * zoom)}px`;
    canvas.style.transform = `scale(${zoom})`;
    canvas.style.setProperty("--branch-size", `${16 / zoom}px`);
    canvas.style.setProperty("--branch-border", `${1 / zoom}px`);
    canvas.style.setProperty("--branch-icon", `${10 / zoom}px`);
    canvas.style.setProperty("--branch-shadow-y", `${1.5 / zoom}px`);
    canvas.style.setProperty("--branch-shadow-blur", `${5 / zoom}px`);
    activeScroller.querySelectorAll(".branch-toggle[data-base-y]").forEach((button) => {
      button.style.top = `${round(Number(button.dataset.baseY) + 9 / zoom)}px`;
    });

    const resetButton = this.shadowRoot.querySelector('[data-zoom="reset"]');
    const zoomText = resetButton?.querySelector("span");
    if (zoomText) zoomText.textContent = `${Math.round(zoom * 100)}%`;
    if (resetButton) resetButton.title = `Về mức mặc định ${Math.round(this._initialZoom() * 100)}%`;

    requestAnimationFrame(() => {
      if (!activeScroller.isConnected) return;
      if (viewport?.mode === "focal") {
        activeScroller.scrollLeft = Math.max(
          0,
          stage.offsetLeft + viewport.treeX * zoom - viewport.viewportX,
        );
        activeScroller.scrollTop = Math.max(
          0,
          stage.offsetTop + viewport.treeY * zoom - viewport.viewportY,
        );
      } else if (viewport?.mode === "center") {
        activeScroller.scrollLeft = Math.max(
          0,
          (activeScroller.scrollWidth - activeScroller.clientWidth) / 2,
        );
        activeScroller.scrollTop = Math.max(0, viewport.top || 0);
      }
    });
  }

  _invalidateTreeCaches() {
    this._normalizedTree = null;
    this._normalizedPeople = [];
    this._completeMaps = null;
    this._collapseFamiliesCache = null;
    this._layoutCache = null;
    this._layoutDirty = true;
    this._initialGenerationApplied = false;
  }

  _scheduleImageRefresh(requestKey, tree) {
    if (this._imageRefreshTimer) clearTimeout(this._imageRefreshTimer);
    this._imageRefreshTimer = null;
    if (!tree?.people?.some((person) => person.image_url)) return;

    const elapsed = Math.max(0, Date.now() - (this._treeLoadedAt || Date.now()));
    const delay = Math.max(1000, TREE_CACHE_MAX_AGE - elapsed);
    this._imageRefreshTimer = setTimeout(() => {
      this._imageRefreshTimer = null;
      if (!this.isConnected) return;
      FAMILY_TREE_CACHE.delete(requestKey);
      if (this._requestKey === requestKey) this._requestKey = null;
      this._maybeLoadTree();
    }, delay);
  }

  _prepareTreeData() {
    if (this._normalizedTree === this._tree) return this._normalizedPeople;
    this._normalizedTree = this._tree;
    this._normalizedPeople = this._normalizePeople(this._tree?.people || []);
    this._completeMaps = this._relationshipMaps(this._normalizedPeople);
    this._collapseFamiliesCache = this._collapseFamilies(
      this._normalizedPeople,
      this._completeMaps,
    );
    this._layoutDirty = true;
    return this._normalizedPeople;
  }

  _getLayout() {
    const people = this._prepareTreeData();
    if (!this._layoutDirty && this._layoutCache) return this._layoutCache;
    this._layoutCache = this._buildLayout(
      people,
      this._completeMaps,
      this._collapseFamiliesCache,
    );
    this._layoutDirty = false;
    return this._layoutCache;
  }

  _content(layout) {
    if (this._error) {
      return `<div class="message error"><ha-icon icon="mdi:alert-circle-outline"></ha-icon><span>${escapeHtml(this._error)}</span></div>`;
    }
    if (this._loading && !layout) {
      return `<div class="message"><div class="spinner"></div><span>Đang tải cây gia phả…</span></div>`;
    }
    if (!this._findSummaryEntity()) {
      return `<div class="message"><ha-icon icon="mdi:family-tree"></ha-icon><span>Đang chờ dữ liệu từ tích hợp Cây Gia Phả…</span></div>`;
    }
    if (!layout || layout.people.length === 0) {
      return `<div class="message empty"><ha-icon icon="mdi:account-plus-outline"></ha-icon><span>Chưa có cá thể trong cây gia phả.</span></div>`;
    }

    const zoom = clampNumber(this._zoom, 0.01, 1.6, this._initialZoom());
    const scene = this._config.show_decorations
      ? this._decorativeScene(layout.width, layout.height)
      : "";
    return `
      <div class="tree-scroll">
        <div class="scaled-stage" style="width:${Math.ceil(layout.width * zoom)}px;height:${Math.ceil(layout.height * zoom)}px">
          <div class="tree-canvas" style="width:${layout.width}px;height:${layout.height}px;transform:scale(${zoom});--branch-size:${16 / zoom}px;--branch-border:${1 / zoom}px;--branch-icon:${10 / zoom}px;--branch-shadow-y:${1.5 / zoom}px;--branch-shadow-blur:${5 / zoom}px">
            ${scene}
            <svg class="connectors" viewBox="0 0 ${layout.width} ${layout.height}" preserveAspectRatio="none" aria-hidden="true">
              ${layout.paths.join("")}
            </svg>
            ${layout.people.map((person) => this._personNode(person)).join("")}
            ${layout.toggles.map((toggle) => this._branchToggle(toggle)).join("")}
          </div>
        </div>
      </div>
    `;
  }

  _normalizePeople(people) {
    const normalized = (people || []).map((person) => ({
      ...person,
      person_id: String(person.person_id || ""),
      level: Math.max(1, Number(person.level) || 1),
      sort_order: Number(person.sort_order) || 0,
      birth_order: Number(person.birth_order) > 0 ? Number(person.birth_order) : null,
      father_id: person.father_id ? String(person.father_id) : null,
      mother_id: person.mother_id ? String(person.mother_id) : null,
      spouse_id: person.spouse_id ? String(person.spouse_id) : null,
      spouse_ids: uniqueStrings(person.spouse_ids || person.spouse_id),
      spouse_order: Math.max(1, Number(person.spouse_order) || 1),
      divorced_spouse_ids: uniqueStrings(person.divorced_spouse_ids),
      step_parent_ids: uniqueStrings(person.step_parent_ids),
      sibling_ids: uniqueStrings(person.sibling_ids),
      is_adopted: Boolean(person.is_adopted),
      is_deceased: Boolean(person.is_deceased),
    }));
    const byId = new Map(normalized.map((person) => [person.person_id, person]));

    normalized.forEach((person) => {
      const relatedId = person.related_person_id ? String(person.related_person_id) : null;
      const related = relatedId ? byId.get(relatedId) : null;
      if (!relatedId) return;
      if (["child", "adopted_child"].includes(person.relationship)) {
        if (!person.father_id && !person.mother_id) {
          if (related?.gender === "female") person.mother_id = relatedId;
          else person.father_id = relatedId;
        }
        if (person.relationship === "adopted_child") person.is_adopted = true;
      } else if (person.relationship === "spouse" && !person.spouse_ids.includes(relatedId)) {
        person.spouse_ids.push(relatedId);
        person.spouse_id = person.spouse_ids[0] || null;
      } else if (person.relationship === "sibling" && !person.sibling_ids.includes(relatedId)) {
        person.sibling_ids.push(relatedId);
      }
    });

    normalized.forEach((person) => {
      if (person.relationship !== "parent" || !person.related_person_id) return;
      const child = byId.get(String(person.related_person_id));
      if (!child) return;
      if (person.gender === "female" && !child.mother_id) child.mother_id = person.person_id;
      else if (!child.father_id) child.father_id = person.person_id;
      else if (!child.mother_id) child.mother_id = person.person_id;
    });

    normalized.forEach((person) => {
      person.spouse_ids = uniqueStrings([...(person.spouse_ids || []), person.spouse_id])
        .filter((id) => id !== person.person_id && byId.has(id));
      person.spouse_id = person.spouse_ids[0] || null;
      person.divorced_spouse_ids = uniqueStrings(person.divorced_spouse_ids).filter((id) => person.spouse_ids.includes(id));
      person.step_parent_ids = uniqueStrings(person.step_parent_ids).filter((id) => id !== person.person_id && byId.has(id) && id !== person.father_id && id !== person.mother_id);
      person._display_spouse_order = person.gender === "female" ? person.spouse_order : null;
    });
    const spouseSets = new Map(normalized.map((person) => [person.person_id, new Set()]));
    normalized.forEach((person) => {
      person.spouse_ids.forEach((spouseId) => {
        if (!byId.has(spouseId) || spouseId === person.person_id) return;
        spouseSets.get(person.person_id).add(spouseId);
        spouseSets.get(spouseId).add(person.person_id);
      });
    });
    normalized.forEach((person) => {
      person.divorced_spouse_ids.forEach((spouseId) => {
        const spouse = byId.get(spouseId);
        if (spouse && !spouse.divorced_spouse_ids.includes(person.person_id)) {
          spouse.divorced_spouse_ids.push(person.person_id);
        }
      });
    });

    normalized
      .filter((person) => person.gender === "male")
      .forEach((husband) => {
        const explicitRanks = new Map(
          husband.spouse_ids.map((wifeId, index) => [wifeId, index + 1])
        );
        const wives = [...(spouseSets.get(husband.person_id) || [])]
          .map((wifeId) => byId.get(wifeId))
          .filter((wife) => wife?.gender === "female")
          .sort((a, b) => {
            const aExplicit = explicitRanks.get(a.person_id);
            const bExplicit = explicitRanks.get(b.person_id);
            if (aExplicit && bExplicit) return aExplicit - bExplicit;
            if (aExplicit) return -1;
            if (bExplicit) return 1;
            return (a.spouse_order || 999) - (b.spouse_order || 999) || familyPersonSort(a, b);
          });
        husband._display_wife_count = wives.length;
        wives.forEach((wife, index) => {
          wife._display_spouse_order = index + 1;
          wife._display_spouse_count = wives.length;
        });
      });

    return normalized.filter((person) => person.person_id);
  }

  _parentIdsForChild(child, maps) {
    return uniqueStrings([child.father_id, child.mother_id, ...(child.step_parent_ids || [])])
      .filter((id) => maps.byId.has(id));
  }

  _isDivorcedPair(firstId, secondId, maps) {
    const first = maps.byId.get(firstId);
    const second = maps.byId.get(secondId);
    return Boolean(first?.divorced_spouse_ids?.includes(secondId) || second?.divorced_spouse_ids?.includes(firstId));
  }

  _collapseFamilies(people, maps) {
    const families = new Map();
    people.forEach((child) => {
      const parentIds = this._parentIdsForChild(child, maps);
      if (!parentIds.length) return;
      const key = familyBranchKey(parentIds);
      if (!families.has(key)) {
        families.set(key, { key, parentIds: [...parentIds], childIds: [] });
      }
      families.get(key).childIds.push(child.person_id);
    });
    return families;
  }

  _applyInitialGenerationCollapse(people, maps, families) {
    if (this._initialGenerationApplied || !people.length) return;

    this._initialGenerationApplied = true;
    if (!this._config.limit_initial_generations) return;

    const limit = Math.round(clampNumber(this._config.initial_generation_limit, 1, 50, 3));
    families.forEach((family, key) => {
      const parentGenerations = family.parentIds
        .map((id) => maps.byId.get(id))
        .filter(Boolean)
        .map((person) => Number(person.level))
        .filter(Number.isFinite);
      const childGenerations = family.childIds
        .map((id) => maps.byId.get(id))
        .filter(Boolean)
        .map((person) => Number(person.level))
        .filter(Number.isFinite);

      if (!parentGenerations.length || !childGenerations.length) return;
      const parentsAreVisible = Math.max(...parentGenerations) <= limit;
      const allChildrenAreAfterLimit = Math.min(...childGenerations) > limit;
      if (parentsAreVisible && allChildrenAreAfterLimit) {
        this._collapsedFamilies.add(key);
      }
    });
  }

  _hiddenDescendantIds(people, maps, families) {
    for (const key of [...this._collapsedFamilies]) {
      if (!families.has(key)) this._collapsedFamilies.delete(key);
    }
    if (!this._collapsedFamilies.size) return new Set();

    const childrenByParent = new Map();
    people.forEach((child) => {
      uniqueStrings([child.father_id, child.mother_id]).forEach((parentId) => {
        if (!childrenByParent.has(parentId)) childrenByParent.set(parentId, new Set());
        childrenByParent.get(parentId).add(child.person_id);
      });
    });

    const hidden = new Set();
    this._collapsedFamilies.forEach((key) => {
      const family = families.get(key);
      if (!family) return;
      const protectedParents = new Set(family.parentIds);
      const queue = [...family.childIds];
      let queueIndex = 0;
      const hiddenForFamily = new Set();
      while (queueIndex < queue.length) {
        const personId = queue[queueIndex];
        queueIndex += 1;
        if (!personId || hiddenForFamily.has(personId) || protectedParents.has(personId)) continue;
        hiddenForFamily.add(personId);
        (maps.spouses.get(personId) || []).forEach((spouseId) => {
          if (!protectedParents.has(spouseId) && !hiddenForFamily.has(spouseId)) queue.push(spouseId);
        });
        (childrenByParent.get(personId) || []).forEach((childId) => {
          if (!hiddenForFamily.has(childId)) queue.push(childId);
        });
      }
      hiddenForFamily.forEach((personId) => hidden.add(personId));
    });
    return hidden;
  }

  _relationshipMaps(people) {
    const byId = new Map(people.map((person) => [person.person_id, person]));
    const spouses = new Map(people.map((person) => [person.person_id, new Set()]));
    const spouseRanks = new Map();
    const siblings = new Map(people.map((person) => [person.person_id, new Set()]));

    people.forEach((person) => {
      uniqueStrings([...(person.spouse_ids || []), person.spouse_id]).forEach((spouseId) => {
        if (!byId.has(spouseId) || spouseId === person.person_id) return;
        spouses.get(person.person_id).add(spouseId);
        spouses.get(spouseId).add(person.person_id);
      });
      person.sibling_ids.forEach((siblingId) => {
        if (!byId.has(siblingId) || siblingId === person.person_id) return;
        siblings.get(person.person_id).add(siblingId);
        siblings.get(siblingId).add(person.person_id);
      });
    });

    [...people]
      .sort((a, b) => (b.spouse_ids?.length || 0) - (a.spouse_ids?.length || 0) || familyPersonSort(a, b))
      .forEach((person) => {
        person.spouse_ids.forEach((spouseId, index) => {
          if (!spouses.get(person.person_id)?.has(spouseId)) return;
          const key = pairKey(person.person_id, spouseId);
          if (!spouseRanks.has(key) || person.spouse_ids.length > 1) {
            spouseRanks.set(key, index + 1);
          }
        });
      });
    people.forEach((person) => {
      [...(spouses.get(person.person_id) || [])].forEach((spouseId) => {
        const key = pairKey(person.person_id, spouseId);
        if (!spouseRanks.has(key)) {
          spouseRanks.set(key, Math.max(1, Number(person.spouse_order) || 1));
        }
      });
    });

    const parentGroups = new Map();
    people.forEach((person) => {
      const key = parentKey(person);
      if (!key) return;
      if (!parentGroups.has(key)) parentGroups.set(key, []);
      parentGroups.get(key).push(person.person_id);
    });
    parentGroups.forEach((ids) => {
      ids.forEach((id) => ids.forEach((other) => {
        if (id !== other) siblings.get(id).add(other);
      }));
    });

    const componentById = new Map();
    const visited = new Set();
    people.forEach((person) => {
      if (visited.has(person.person_id)) return;
      const stack = [person.person_id];
      const component = [];
      while (stack.length) {
        const id = stack.pop();
        if (visited.has(id)) continue;
        visited.add(id);
        component.push(id);
        siblings.get(id)?.forEach((next) => {
          if (!visited.has(next)) stack.push(next);
        });
      }
      const key = component.length > 1 ? `siblings:${[...component].sort().join("|")}` : null;
      component.forEach((id) => componentById.set(id, key));
    });

    return { byId, spouses, spouseRanks, siblings, componentById };
  }

  _buildLayout(people, providedCompleteMaps = null, providedCollapseFamilies = null) {
    const completePeople = people;
    if (!completePeople.length) {
      return {
        width: Math.max(this.clientWidth - 24, 340),
        height: 240,
        people: [],
        paths: [],
        toggles: [],
        union_sources: {},
      };
    }
    const completeMaps = providedCompleteMaps || this._relationshipMaps(completePeople);
    const collapseFamilies = providedCollapseFamilies || this._collapseFamilies(completePeople, completeMaps);
    this._applyInitialGenerationCollapse(completePeople, completeMaps, collapseFamilies);
    const hiddenIds = this._hiddenDescendantIds(completePeople, completeMaps, collapseFamilies);
    people = completePeople.filter((person) => !hiddenIds.has(person.person_id));

    const nodeWidth = clampNumber(this._config.node_width, 118, 260, 156);
    const avatarSize = clampNumber(this._config.avatar_size, 48, 120, 70);
    const hGap = clampNumber(this._config.horizontal_spacing, 10, 160, 34);
    const vGap = clampNumber(this._config.vertical_spacing, 46, 190, 84);
    const coupleGap = Math.max(26, Math.round(hGap * 0.8));
    const familyGap = Math.max(58, Math.round(hGap * 2));
    const labelTop = avatarSize + 8;
    const labelHeight = this._config.show_dates ? (this._config.show_age ? 78 : 66) : 54;
    const nodeHeight = labelTop + labelHeight;
    const marginX = 54;
    const marginTop = 24;
    const maps = this._relationshipMaps(people);

    const rows = new Map();
    people.forEach((person) => {
      if (!rows.has(person.level)) rows.set(person.level, []);
      rows.get(person.level).push(person);
    });
    const levels = [...rows.keys()].sort((a, b) => a - b);
    const unitsByLevel = new Map();
    const unitByPerson = new Map();

    const setBaseGeometry = (unit) => {
      unit.memberGaps = unit.members.map((_, index) => index === 0 ? 0 : coupleGap);
      unit.memberOffsets = [0];
      for (let index = 1; index < unit.members.length; index += 1) {
        unit.memberOffsets[index] = unit.memberOffsets[index - 1] + nodeWidth + unit.memberGaps[index];
      }
      unit.width = unit.memberOffsets[unit.memberOffsets.length - 1] + nodeWidth;
      const anchorIndex = Math.max(0, unit.memberIndex.get(unit.anchor.person_id) ?? -1);
      unit.anchorOffset = unit.memberOffsets[anchorIndex] + nodeWidth / 2;
      unit.footLeft = unit.anchorOffset;
      unit.footRight = unit.width - unit.anchorOffset;
    };

    levels.forEach((level) => {
      const row = rows.get(level) || [];
      const rowIds = new Set(row.map((person) => person.person_id));
      const assigned = new Set();
      const units = [];
      [...row].sort(familyPersonSort).forEach((person) => {
        if (assigned.has(person.person_id)) return;
        const stack = [person.person_id];
        const component = [];
        while (stack.length) {
          const id = stack.pop();
          if (assigned.has(id) || !rowIds.has(id)) continue;
          assigned.add(id);
          const member = maps.byId.get(id);
          if (member) component.push(member);
          (maps.spouses.get(id) || []).forEach((spouseId) => {
            if (!assigned.has(spouseId) && rowIds.has(spouseId)) stack.push(spouseId);
          });
        }
        const members = orderSpouseGroup(component.length ? component : [person], maps);
        const spouseHub = chooseSpouseHub(members, maps);
        const anchor = chooseFamilyAnchor(members, maps);
        const parentIds = uniqueStrings([anchor.father_id, anchor.mother_id]).filter((id) => maps.byId.has(id));
        const unit = {
          id: `unit:${level}:${members.map((member) => member.person_id).sort().join("|")}`,
          level,
          members,
          spouseHubId: spouseHub?.person_id || null,
          anchor,
          parentIds,
          parentKey: parentIds.length ? `parents:${[...parentIds].sort().join("|")}` : null,
          childBranches: [],
          parentBranch: null,
          left: null,
          memberIndex: new Map(members.map((member, index) => [member.person_id, index])),
          memberIds: new Set(members.map((member) => member.person_id)),
        };
        setBaseGeometry(unit);
        units.push(unit);
        members.forEach((member) => unitByPerson.set(member.person_id, unit));
      });
      unitsByLevel.set(level, units);
    });

    const sourceOffsetInUnit = (unit, parentIds) => {
      const parentIndexes = uniqueStrings(parentIds)
        .map((id) => unit.memberIndex.get(id) ?? -1)
        .filter((index) => index >= 0);
      if (!parentIndexes.length) return unit.anchorOffset;
      if (parentIndexes.length === 1) return unit.memberOffsets[parentIndexes[0]] + nodeWidth / 2;

      const sortedIndexes = [...parentIndexes].sort((a, b) => a - b);
      if (sortedIndexes.length === 2 && sortedIndexes[1] === sortedIndexes[0] + 1) {
        const rightIndex = sortedIndexes[1];
        const gap = unit.memberGaps[rightIndex] || coupleGap;
        return unit.memberOffsets[rightIndex] - gap / 2;
      }

      const hubIndex = unit.spouseHubId
        ? (unit.memberIndex.get(unit.spouseHubId) ?? -1)
        : -1;
      if (hubIndex >= 0 && parentIndexes.includes(hubIndex) && parentIndexes.length === 2) {
        const spouseIndex = parentIndexes.find((index) => index !== hubIndex);
        if (spouseIndex < hubIndex) {
          const gapIndex = spouseIndex + 1;
          const gap = unit.memberGaps[gapIndex] || coupleGap;
          return unit.memberOffsets[spouseIndex] + nodeWidth + gap / 2;
        }
        if (spouseIndex > hubIndex) {
          const gap = unit.memberGaps[spouseIndex] || coupleGap;
          return unit.memberOffsets[spouseIndex] - gap / 2;
        }
      }

      return parentIndexes
        .map((index) => unit.memberOffsets[index] + nodeWidth / 2)
        .reduce((sum, value) => sum + value, 0) / parentIndexes.length;
    };

    const recomputeUnitGeometry = (unit) => {
      const branchByPair = new Map();
      unit.childBranches.forEach((branch) => {
        if (branch.parentIds.length >= 2) branchByPair.set(pairKey(branch.parentIds[0], branch.parentIds[1]), branch);
      });

      unit.memberGaps = unit.members.map((_, index) => index === 0 ? 0 : coupleGap);
      const hubIndex = unit.spouseHubId
        ? (unit.memberIndex.get(unit.spouseHubId) ?? -1)
        : -1;
      const hub = hubIndex >= 0 ? unit.members[hubIndex] : null;
      if (hub) {
        const spouseIndexes = unit.members
          .map((member, index) => ({ member, index }))
          .filter(({ member }) => maps.spouses.get(hub.person_id)?.has(member.person_id));
        const tuneSide = (items, direction) => {
          for (let itemIndex = 1; itemIndex < items.length; itemIndex += 1) {
            const previous = items[itemIndex - 1];
            const current = items[itemIndex];
            const previousBranch = branchByPair.get(pairKey(hub.person_id, previous.member.person_id));
            const currentBranch = branchByPair.get(pairKey(hub.person_id, current.member.person_id));
            if (!previousBranch || !currentBranch) continue;
            const requiredSeparation = direction === "left"
              ? currentBranch.right + previousBranch.left + familyGap
              : previousBranch.right + currentBranch.left + familyGap;
            const previousGapIndex = previous.index < hubIndex ? previous.index + 1 : previous.index;
            const currentGapIndex = current.index < hubIndex ? current.index + 1 : current.index;
            const previousGap = unit.memberGaps[previousGapIndex] || coupleGap;
            unit.memberGaps[currentGapIndex] = Math.max(
              coupleGap,
              2 * (requiredSeparation - nodeWidth) - previousGap,
            );
          }
        };
        tuneSide(
          spouseIndexes.filter(({ index }) => index < hubIndex).sort((a, b) => b.index - a.index),
          "left",
        );
        tuneSide(
          spouseIndexes.filter(({ index }) => index > hubIndex).sort((a, b) => a.index - b.index),
          "right",
        );
      }

      const rebuildMemberOffsets = () => {
        unit.memberOffsets = [0];
        for (let index = 1; index < unit.members.length; index += 1) {
          unit.memberOffsets[index] = unit.memberOffsets[index - 1] + nodeWidth + unit.memberGaps[index];
        }
      };

      // A child unit may be wider than its own anchor card because it can also
      // contain that child's spouse(s). Compare complete branch footprints so
      // children from separate marriages never occupy the same horizontal area.
      const spreadOverlappingMarriageBranches = () => {
        if (unit.childBranches.length < 2 || unit.memberGaps.length < 2) return;
        const maxPasses = Math.max(8, unit.childBranches.length * unit.memberGaps.length * 4);
        for (let pass = 0; pass < maxPasses; pass += 1) {
          rebuildMemberOffsets();
          const entries = unit.childBranches
            .map((branch) => ({ branch, source: sourceOffsetInUnit(unit, branch.parentIds) }))
            .sort((a, b) => a.source - b.source);
          let overlapPair = null;
          for (let index = 1; index < entries.length; index += 1) {
            const left = entries[index - 1];
            const right = entries[index];
            const overlap = left.source + left.branch.right + familyGap
              - (right.source - right.branch.left);
            if (overlap > 0.5) {
              overlapPair = { left, right, overlap };
              break;
            }
          }
          if (!overlapPair) return;

          const baseSeparation = overlapPair.right.source - overlapPair.left.source;
          const responsiveGaps = [];
          for (let gapIndex = 1; gapIndex < unit.memberGaps.length; gapIndex += 1) {
            unit.memberGaps[gapIndex] += 1;
            rebuildMemberOffsets();
            const separation = sourceOffsetInUnit(unit, overlapPair.right.branch.parentIds)
              - sourceOffsetInUnit(unit, overlapPair.left.branch.parentIds);
            unit.memberGaps[gapIndex] -= 1;
            const response = separation - baseSeparation;
            if (response > 0.0001) responsiveGaps.push({ gapIndex, response });
          }
          rebuildMemberOffsets();

          const totalResponse = responsiveGaps.reduce((sum, item) => sum + item.response, 0);
          if (totalResponse <= 0.0001) return;
          const increment = (overlapPair.overlap + 1) / totalResponse;
          responsiveGaps.forEach(({ gapIndex }) => {
            unit.memberGaps[gapIndex] += increment;
          });
        }
        rebuildMemberOffsets();
      };

      spreadOverlappingMarriageBranches();
      rebuildMemberOffsets();
      unit.width = unit.memberOffsets[unit.memberOffsets.length - 1] + nodeWidth;
      const anchorIndex = Math.max(0, unit.memberIndex.get(unit.anchor.person_id) ?? -1);
      unit.anchorOffset = unit.memberOffsets[anchorIndex] + nodeWidth / 2;

      let minRelative = -unit.anchorOffset;
      let maxRelative = unit.width - unit.anchorOffset;
      unit.childBranches.forEach((branch) => {
        const sourceRelative = sourceOffsetInUnit(unit, branch.parentIds) - unit.anchorOffset;
        minRelative = Math.min(minRelative, sourceRelative - branch.left);
        maxRelative = Math.max(maxRelative, sourceRelative + branch.right);
      });
      unit.footLeft = -minRelative;
      unit.footRight = maxRelative;
    };

    const branchGroups = [];
    [...levels].reverse().forEach((level) => {
      const groups = new Map();
      (unitsByLevel.get(level) || []).forEach((unit) => {
        if (!unit.parentKey) return;
        const parentUnits = uniqueStrings(unit.parentIds.map((id) => unitByPerson.get(id)?.id));
        if (!parentUnits.length) return;
        const parentUnit = unitByPerson.get(unit.parentIds.find((id) => unitByPerson.has(id)));
        if (!parentUnit || parentUnit.level >= unit.level) return;
        const key = `${parentUnit.id}:${unit.parentKey}`;
        if (!groups.has(key)) groups.set(key, { parentUnit, parentIds: unit.parentIds, childUnits: [] });
        groups.get(key).childUnits.push(unit);
      });

      const touchedParents = new Set();
      groups.forEach(({ parentUnit, parentIds, childUnits }) => {
        childUnits.sort((a, b) => familyPersonSort(a.anchor, b.anchor));
        let cursor = 0;
        const placements = [];
        childUnits.forEach((childUnit, index) => {
          const anchorCenter = cursor + childUnit.footLeft;
          placements.push({ unit: childUnit, anchorCenter, offset: 0 });
          cursor += childUnit.footLeft + childUnit.footRight + (index < childUnits.length - 1 ? hGap : 0);
        });
        const width = Math.max(nodeWidth, cursor);
        const anchorSpanCenter = placements.length
          ? (placements[0].anchorCenter + placements[placements.length - 1].anchorCenter) / 2
          : width / 2;
        placements.forEach((placement) => { placement.offset = placement.anchorCenter - anchorSpanCenter; });
        const branch = {
          parentUnit,
          parentIds: uniqueStrings(parentIds),
          childUnits,
          placements,
          placementByUnit: new Map(placements.map((placement) => [placement.unit.id, placement])),
          width,
          left: anchorSpanCenter,
          right: width - anchorSpanCenter,
        };
        placements.forEach((placement) => { placement.unit.parentBranch = branch; });
        parentUnit.childBranches.push(branch);
        touchedParents.add(parentUnit);
        branchGroups.push(branch);
      });
      touchedParents.forEach(recomputeUnitGeometry);
    });

    const positions = new Map();
    const unitPositions = new Map();
    levels.forEach((level, rowIndex) => {
      const units = unitsByLevel.get(level) || [];
      const anchored = [];
      const free = [];
      units.forEach((unit) => {
        const branch = unit.parentBranch;
        const parentLeft = branch ? unitPositions.get(branch.parentUnit.id) : null;
        const placement = branch?.placementByUnit.get(unit.id);
        if (branch && parentLeft !== undefined && parentLeft !== null && placement) {
          const sourceX = parentLeft + sourceOffsetInUnit(branch.parentUnit, branch.parentIds);
          unit.left = sourceX + placement.offset - unit.anchorOffset;
          anchored.push(unit);
        } else {
          free.push(unit);
        }
      });

      let cursor = anchored.length
        ? Math.max(...anchored.map((unit) => unit.left + unit.anchorOffset + unit.footRight)) + familyGap
        : 0;
      free.sort((a, b) => familyPersonSort(a.anchor, b.anchor)).forEach((unit) => {
        unit.left = cursor + unit.footLeft - unit.anchorOffset;
        cursor += unit.footLeft + unit.footRight + familyGap;
      });

      const y = marginTop + rowIndex * (nodeHeight + vGap);
      units.forEach((unit) => {
        unitPositions.set(unit.id, unit.left);
        unit.members.forEach((member, memberIndex) => {
          positions.set(member.person_id, {
            ...member,
            x: unit.left + unit.memberOffsets[memberIndex],
            y,
            nodeWidth,
            nodeHeight,
            avatarSize,
            labelTop,
            labelHeight,
            unit_id: unit.id,
            has_family_order: Boolean(parentKey(member) || (maps.siblings.get(member.person_id)?.size || 0)),
          });
        });
      });
    });

    const positioned = [...positions.values()];
    const rawMinX = Math.min(...positioned.map((person) => person.x));
    const rawMaxX = Math.max(...positioned.map((person) => person.x + person.nodeWidth));
    const contentWidth = Math.max(nodeWidth, rawMaxX - rawMinX);
    const available = Math.max(this.clientWidth - 24, 340);
    const width = Math.max(contentWidth + marginX * 2, available);
    const extraCentering = Math.max(0, width - (contentWidth + marginX * 2)) / 2;
    const globalShift = marginX - rawMinX + extraCentering;
    positioned.forEach((person) => { person.x += globalShift; });
    unitsByLevel.forEach((units) => units.forEach((unit) => { unit.left += globalShift; }));
    const positionedByUnit = new Map();
    positioned.forEach((person) => {
      if (!positionedByUnit.has(person.unit_id)) positionedByUnit.set(person.unit_id, []);
      positionedByUnit.get(person.unit_id).push(person);
    });
    positionedByUnit.forEach((members) => members.sort((a, b) => a.x - b.x));

    const height = marginTop * 2 + levels.length * nodeHeight + Math.max(0, levels.length - 1) * vGap + 24;
    const paths = [];
    const drawnCouples = new Set();
    const unionSources = new Map();

    unitsByLevel.forEach((units) => {
      units.forEach((unit) => {
        unit.members.forEach((member) => {
          (maps.spouses.get(member.person_id) || []).forEach((spouseId) => {
            if (!unit.memberIds.has(spouseId)) return;
            const key = pairKey(member.person_id, spouseId);
            if (unionSources.has(key)) return;
            const first = positions.get(member.person_id);
            const second = positions.get(spouseId);
            if (!first || !second) return;
            unionSources.set(key, {
              x: unit.left + sourceOffsetInUnit(unit, [member.person_id, spouseId]),
              y: marriageSourceY([first, second]),
            });
          });
        });
      });
    });

    maps.spouses.forEach((spouseIds, personId) => {
      spouseIds.forEach((spouseId) => {
        const key = pairKey(personId, spouseId);
        if (drawnCouples.has(key)) return;
        const first = positions.get(personId);
        const second = positions.get(spouseId);
        if (!first || !second || first.level !== second.level) return;
        const [left, right] = first.x <= second.x ? [first, second] : [second, first];
        const union = unionSources.get(key);
        const y = union?.y ?? marriageSourceY([first, second]);
        let lineStart = left.x + left.nodeWidth;
        let lineEnd = right.x;
        if (union && first.unit_id === second.unit_id) {
          const unitMembers = positionedByUnit.get(first.unit_id) || [];
          const leftNeighbor = [...unitMembers]
            .reverse()
            .find((candidate) => candidate.x + candidate.nodeWidth <= union.x + 0.5);
          const rightNeighbor = unitMembers
            .find((candidate) => candidate.x >= union.x - 0.5);
          if (leftNeighbor && rightNeighbor) {
            lineStart = leftNeighbor.x + leftNeighbor.nodeWidth;
            lineEnd = rightNeighbor.x;
          }
        }
        const divorceClass = this._isDivorcedPair(personId, spouseId, maps) ? " relation-divorced" : "";
        paths.push(`<path class="relation relation-spouse${divorceClass}" d="M ${round(lineStart)} ${round(y)} H ${round(lineEnd)}" />`);
        drawnCouples.add(key);
      });
    });

    const childGroups = new Map();
    [...positions.values()].forEach((child) => {
      const parentIds = this._parentIdsForChild(child, maps).filter((id) => positions.has(id));
      if (!parentIds.length) return;
      const key = familyBranchKey(parentIds);
      if (!childGroups.has(key)) childGroups.set(key, { key, parentIds: new Set(parentIds), children: [] });
      const group = childGroups.get(key);
      parentIds.forEach((id) => group.parentIds.add(id));
      group.children.push(child);
    });

    const toggles = [];
    const orderedGroups = [...childGroups.values()].sort((a, b) => {
      const aIds = [...a.parentIds];
      const bIds = [...b.parentIds];
      const aSource = aIds.length >= 2 ? unionSources.get(pairKey(aIds[0], aIds[1]))?.x : positions.get(aIds[0])?.x;
      const bSource = bIds.length >= 2 ? unionSources.get(pairKey(bIds[0], bIds[1]))?.x : positions.get(bIds[0])?.x;
      return (aSource || 0) - (bSource || 0);
    });

    orderedGroups.forEach(({ key, parentIds, children }, groupIndex) => {
      const parents = [...parentIds].map((id) => positions.get(id)).filter(Boolean);
      if (!parents.length || !children.length) return;
      const sortedParents = [...parents].sort((a, b) => a.x - b.x);
      let sourceX;
      let sourceY;
      if (sortedParents.length >= 2) {
        const coupleKey = pairKey(sortedParents[0].person_id, sortedParents[1].person_id);
        const union = unionSources.get(coupleKey);
        sourceX = union?.x ?? sortedParents.reduce((sum, parent) => sum + parent.x + parent.nodeWidth / 2, 0) / sortedParents.length;
        sourceY = union?.y ?? marriageSourceY(sortedParents);
        const leftParent = sortedParents[0];
        const rightParent = sortedParents[sortedParents.length - 1];
        if (!drawnCouples.has(coupleKey)) {
          paths.push(`<path class="relation relation-parent-union" d="M ${round(leftParent.x + leftParent.nodeWidth)} ${round(sourceY)} H ${round(rightParent.x)}" />`);
          drawnCouples.add(coupleKey);
        }
      } else {
        const parent = sortedParents[0];
        sourceX = parent.x + parent.nodeWidth / 2;
        sourceY = parent.y + parent.labelTop + parent.labelHeight;
      }

      const orderedChildren = [...children].sort((a, b) => a.x - b.x);
      const targetY = Math.min(...orderedChildren.map((child) => child.y));
      const availableGap = Math.max(36, targetY - sourceY);
      const laneOffset = (groupIndex % 4) * 7;
      const proposedBarY = sourceY + Math.min(66 + laneOffset, Math.max(26 + laneOffset, availableGap * 0.5));
      const barY = Math.min(targetY - 18, proposedBarY);
      const childCenters = orderedChildren.map((child) => child.x + child.nodeWidth / 2);
      const minX = Math.min(sourceX, ...childCenters);
      const maxX = Math.max(sourceX, ...childCenters);

      toggles.push({
        key,
        x: sourceX,
        y: sourceY,
        collapsed: false,
        childCount: orderedChildren.length,
      });
      paths.push(`<path class="relation relation-trunk" d="M ${round(sourceX)} ${round(sourceY)} V ${round(barY)}" />`);
      if (maxX - minX > 0.5) {
        paths.push(`<path class="relation relation-sibling-bar" d="M ${round(minX)} ${round(barY)} H ${round(maxX)}" />`);
      }
      orderedChildren.forEach((child) => {
        const childX = child.x + child.nodeWidth / 2;
        const isStepChild = (child.step_parent_ids || []).length > 0;
        const relationClass = child.is_adopted ? "relation-adopted" : (isStepChild ? "relation-stepchild" : "relation-child");
        paths.push(`<path class="relation ${relationClass}" d="M ${round(childX)} ${round(barY)} V ${round(child.y)}" />`);
      });
    });

    collapseFamilies.forEach((family, key) => {
      if (!this._collapsedFamilies.has(key)) return;
      const parents = family.parentIds.map((id) => positions.get(id)).filter(Boolean).sort((a, b) => a.x - b.x);
      if (!parents.length) return;
      let sourceX;
      let sourceY;
      if (parents.length >= 2) {
        const union = unionSources.get(pairKey(parents[0].person_id, parents[1].person_id));
        sourceX = union?.x ?? parents.reduce((sum, parent) => sum + parent.x + parent.nodeWidth / 2, 0) / parents.length;
        sourceY = union?.y ?? marriageSourceY(parents);
      } else {
        sourceX = parents[0].x + parents[0].nodeWidth / 2;
        sourceY = parents[0].y + parents[0].labelTop + parents[0].labelHeight;
      }
      toggles.push({
        key,
        x: sourceX,
        y: sourceY,
        collapsed: true,
        childCount: family.childIds.length,
      });
    });

    const siblingComponents = new Map();
    [...positions.values()].forEach((person) => {
      if (person.father_id || person.mother_id) return;
      const key = maps.componentById.get(person.person_id);
      if (!key) return;
      if (!siblingComponents.has(key)) siblingComponents.set(key, []);
      siblingComponents.get(key).push(person);
    });
    siblingComponents.forEach((siblings) => {
      const row = siblings.filter((person) => person.level === siblings[0].level).sort((a, b) => a.x - b.x);
      if (row.length < 2) return;
      const y = row[0].y + row[0].labelTop + row[0].labelHeight + 12;
      paths.push(`<path class="relation relation-explicit-sibling" d="M ${round(row[0].x + row[0].nodeWidth / 2)} ${round(y)} H ${round(row[row.length - 1].x + row[row.length - 1].nodeWidth / 2)}" />`);
    });

    const positionedPeople = [...positions.values()].sort((a, b) => a.level - b.level || a.x - b.x);
    return {
      width,
      height,
      people: positionedPeople,
      paths,
      toggles,
      union_sources: Object.fromEntries([...unionSources.entries()].map(([key, value]) => [key, value.x])),
    };
  }

  _personNode(person) {
    const gender = ["male", "female", "other"].includes(person.gender) ? person.gender : "other";
    const deceasedClass = person.is_deceased && this._config.deceased_grayscale ? " deceased" : "";
    const defaultAvatar = defaultAvatarUrl(person.gender);
    const image = person.image_url
      ? `<img src="${escapeAttr(person.image_url)}" alt="${escapeAttr(person.full_name)}" loading="lazy" draggable="false" data-fallback-src="${escapeAttr(defaultAvatar)}" data-fallback="${escapeAttr(initials(person.full_name))}" data-fallback-class="avatar-placeholder" />`
      : `<img src="${escapeAttr(defaultAvatar)}" alt="Ảnh đại diện mặc định của ${escapeAttr(person.full_name)}" loading="lazy" draggable="false" data-fallback="${escapeAttr(initials(person.full_name))}" data-fallback-class="avatar-placeholder" />`;
    const role = this._personRole(person);
    const dates = this._formatDates(person);

    return `
      <article
        class="person-node gender-${gender}${deceasedClass}"
        data-person-id="${escapeAttr(person.person_id)}"
        tabindex="0"
        role="button"
        aria-label="${escapeAttr(person.full_name)}"
        style="left:${round(person.x)}px;top:${round(person.y)}px;width:${person.nodeWidth}px;height:${person.nodeHeight}px;--avatar:${person.avatarSize}px;--label-top:${person.labelTop}px;--label-height:${person.labelHeight}px"
      >
        <div class="person-label">
          ${personNameMarkup(person.full_name || "Không rõ tên")}
          <span>${escapeHtml(role)}</span>
          ${this._config.show_dates && dates ? `<small>${escapeHtml(dates)}</small>` : ""}
        </div>
        <div class="avatar-wrap">
          ${image}
          ${person.is_adopted ? '<span class="adopted-mark" title="Con nuôi">N</span>' : ((person.step_parent_ids || []).length ? '<span class="stepchild-mark" title="Con riêng của vợ/chồng">R</span>' : "")}
          ${person.is_deceased ? '<span class="memorial" title="Đã mất" aria-label="Đã mất"><ha-icon icon="mdi:candle"></ha-icon></span>' : ""}
        </div>
      </article>
    `;
  }

  _branchToggle(toggle) {
    const action = toggle.collapsed ? "Hiện lại" : "Ẩn";
    const icon = toggle.collapsed ? "mdi:plus" : "mdi:minus";
    return `
      <button
        class="branch-toggle${toggle.collapsed ? " is-collapsed" : ""}"
        data-family-key="${escapeAttr(toggle.key)}"
        data-base-y="${round(toggle.y)}"
        style="left:${round(toggle.x)}px;top:${round(toggle.y + 9 / this._zoom)}px"
        aria-expanded="${toggle.collapsed ? "false" : "true"}"
        aria-label="${action} nhánh gia đình có ${toggle.childCount} người con"
        title="${action} toàn bộ nhánh con cháu"
      ><ha-icon icon="${icon}"></ha-icon></button>
    `;
  }

  _personRole(person) {
    const hasParents = Boolean(person.father_id || person.mother_id);
    const hasSpouse = (person.spouse_ids || []).length > 0 || Boolean(person.spouse_id);
    const order = Number(person.birth_order) > 0 ? `Con thứ ${Number(person.birth_order)}` : "";
    if (person.is_adopted) return ["Con nuôi", order].filter(Boolean).join(" · ");
    if ((person.step_parent_ids || []).length) return ["Con riêng", order].filter(Boolean).join(" · ");
    if (hasParents) return order || `Thế hệ ${person.level}`;
    if (hasSpouse) {
      if (person.gender === "male") return person.level === 1 ? "Gốc gia phả" : "Chồng";
      if (person.gender === "female") return wifeRankLabel(person._display_spouse_order || person.spouse_order, person._display_spouse_count || 1);
      return "Vợ / chồng";
    }
    if (person.level === 1) return "Gốc gia phả";
    return `Thế hệ ${person.level}`;
  }

  _summary(stats) {
    const items = [
      ["mdi:account-group-outline", "Tổng", stats.total ?? 0],
      ["mdi:gender-male", "Nam", stats.male ?? 0],
      ["mdi:gender-female", "Nữ", stats.female ?? 0],
      ["mdi:heart-pulse", "Còn sống", stats.living ?? 0],
      ["mdi:candle", "Đã mất", stats.deceased ?? 0],
      ["mdi:layers-triple-outline", "Thế hệ", stats.levels ?? 0],
    ];
    return `<div class="summary">${items.map(([icon, label, value]) => `
      <div class="summary-item">
        <ha-icon icon="${icon}"></ha-icon>
        <span>${label}</span>
        <strong>${Number(value) || 0}</strong>
      </div>`).join("")}</div>`;
  }

  _detailPanel(person, people, providedMaps = null) {
    const maps = providedMaps || this._relationshipMaps(people);
    const father = person.father_id ? maps.byId.get(person.father_id) : null;
    const mother = person.mother_id ? maps.byId.get(person.mother_id) : null;
    const stepParents = (person.step_parent_ids || []).map((id) => maps.byId.get(id)).filter(Boolean);
    const spouseItems = [...(maps.spouses.get(person.person_id) || [])]
      .map((id) => ({
        spouse: maps.byId.get(id),
        rank: maps.spouseRanks.get(pairKey(person.person_id, id)) || Number.POSITIVE_INFINITY,
      }))
      .filter((item) => item.spouse)
      .sort((a, b) => a.rank - b.rank || familyPersonSort(a.spouse, b.spouse));
    const wifeCount = person.gender === "male"
      ? spouseItems.filter((item) => item.spouse.gender === "female").length
      : 0;
    const spouseNames = spouseItems
      .map((item) => {
        const divorced = this._isDivorcedPair(person.person_id, item.spouse.person_id, maps);
        let label = item.spouse.full_name;
        if (person.gender === "male" && item.spouse.gender === "female") {
          const rank = Number.isFinite(item.rank) ? item.rank : item.spouse.spouse_order;
          label = `${wifeRankLabel(rank, wifeCount)}: ${item.spouse.full_name}`;
        }
        return { label: `${label}${divorced ? " (đã ly hôn)" : ""}`, divorced };
      })
      .sort((a, b) => Number(a.divorced) - Number(b.divorced))
      .map((item) => item.label)
      .join("\n");
    const siblingNames = [...(maps.siblings.get(person.person_id) || [])]
      .map((id) => maps.byId.get(id))
      .filter(Boolean)
      .sort(familyPersonSort)
      .map((item) => item.full_name)
      .join(", ");
    const defaultAvatar = defaultAvatarUrl(person.gender);
    const image = person.image_url
      ? `<img src="${escapeAttr(person.image_url)}" alt="${escapeAttr(person.full_name)}" data-fallback-src="${escapeAttr(defaultAvatar)}" data-fallback="${escapeAttr(initials(person.full_name))}" data-fallback-class="detail-placeholder" />`
      : `<img src="${escapeAttr(defaultAvatar)}" alt="Ảnh đại diện mặc định của ${escapeAttr(person.full_name)}" data-fallback="${escapeAttr(initials(person.full_name))}" data-fallback-class="detail-placeholder" />`;
    const rows = [
      ["Giới tính", GENDER_LABEL[person.gender] || "Khác"],
      ["Thế hệ", person.level],
      ["Con thứ", Number(person.birth_order) > 0 ? Number(person.birth_order) : "—"],
      ["Quan hệ cha mẹ", person.is_adopted ? "Con nuôi" : ((person.step_parent_ids || []).length ? "Con riêng của vợ/chồng" : (father && mother ? "Con đẻ chung" : (father || mother ? "Con ruột (chưa đủ thông tin cha/mẹ)" : "—")))],
      ["Cha", father?.full_name || "—"],
      ["Mẹ", mother?.full_name || "—"],
      ["Cha/mẹ kế", stepParents.map((item) => item.full_name).join(", ") || "—"],
      ["Vợ / chồng", spouseNames || "—"],
      ["Anh chị em ruột", siblingNames || "—"],
      ["Ngày sinh", formatPersonDate(person, "birth") || "Không rõ"],
      ["Ngày mất", person.is_deceased ? formatPersonDate(person, "death") || "Không rõ" : "—"],
      ["Tuổi", calculateAgeText(person)],
    ];
    return `
      <div class="detail-backdrop">
        <section class="detail-panel" role="dialog" aria-modal="true" aria-label="Thông tin cá thể">
          <button class="detail-close" aria-label="Đóng"><ha-icon icon="mdi:close"></ha-icon></button>
          <div class="detail-hero">${image}</div>
          <h2>${escapeHtml(person.full_name)}</h2>
          <p class="detail-role">${escapeHtml(this._personRole(person))}</p>
          <div class="detail-grid">
            ${rows.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value ?? "—"))}</strong></div>`).join("")}
          </div>
          ${person.details ? `<div class="detail-notes"><h3>Chi tiết</h3><p>${escapeHtml(person.details).replace(/\n/g, "<br>")}</p></div>` : ""}
        </section>
      </div>
    `;
  }

  _zoomControls() {
    return `
      <div class="zoom-controls" aria-label="Thu phóng và căn cây">
        <button class="fit-tree-button" data-fit-tree title="Hiện tất cả nhánh và căn vừa toàn bộ cây" aria-label="Hiện tất cả nhánh và căn vừa toàn bộ cây"><ha-icon icon="mdi:fit-to-screen-outline"></ha-icon></button>
        <button data-zoom="out" title="Thu nhỏ"><ha-icon icon="mdi:magnify-minus-outline"></ha-icon></button>
        <button data-zoom="reset" title="Về mức mặc định ${Math.round(this._initialZoom() * 100)}%"><span>${Math.round(this._zoom * 100)}%</span></button>
        <button data-zoom="in" title="Phóng to"><ha-icon icon="mdi:magnify-plus-outline"></ha-icon></button>
      </div>
    `;
  }


  _pdfExportButton() {
    return `
      <button class="pdf-export-button" data-export-pdf title="Xuất PDF poster khổ tự động, giữ vector chất lượng cao" aria-label="Xuất PDF">
        <ha-icon icon="mdi:file-pdf-box"></ha-icon>
        <span>Xuất PDF</span>
      </button>
    `;
  }

  _renderedHaIconSvg(icon) {
    const root = this.shadowRoot;
    if (!root) return "";
    const escaped = typeof CSS !== "undefined" && CSS.escape ? CSS.escape(icon) : icon.replace(/"/g, "\\\"");
    const source = root.querySelector(`.print-icon-cache ha-icon[icon="${escaped}"]`)
      || root.querySelector(`ha-icon[icon="${escaped}"]`);
    if (!source) return "";

    const findSvg = (node, seen = new Set()) => {
      if (!node || seen.has(node)) return null;
      seen.add(node);
      if (node.nodeType === 1 && String(node.localName || "").toLowerCase() === "svg") return node;
      if (node.shadowRoot) {
        const nested = findSvg(node.shadowRoot, seen);
        if (nested) return nested;
      }
      for (const child of Array.from(node.children || node.childNodes || [])) {
        const nested = findSvg(child, seen);
        if (nested) return nested;
      }
      return null;
    };

    const svg = findSvg(source);
    if (!svg) return "";
    const clone = svg.cloneNode(true);
    clone.removeAttribute("width");
    clone.removeAttribute("height");
    clone.setAttribute("aria-hidden", "true");
    clone.setAttribute("focusable", "false");
    clone.classList.add("print-mdi-svg");
    return clone.outerHTML;
  }

  _printIcon(icon) {
    const svg = this._renderedHaIconSvg(icon);
    if (svg) return svg;
    // Extremely defensive fallback. Normally the hidden icon cache above is already rendered by HA.
    return `<span class="print-icon-fallback" aria-hidden="true"></span>`;
  }

  _printPersonNode(person) {
    return this._personNode(person)
      .replace(/ loading="lazy"/g, ' loading="eager"')
      .replace('<ha-icon icon="mdi:candle"></ha-icon>', `<span class="print-candle-icon" aria-hidden="true">${this._printIcon("mdi:candle")}</span>`);
  }

  _printSummary(stats = {}) {
    const items = [
      ["mdi:account-group-outline", "Tổng", stats.total ?? 0],
      ["mdi:gender-male", "Nam", stats.male ?? 0],
      ["mdi:gender-female", "Nữ", stats.female ?? 0],
      ["mdi:heart-pulse", "Còn sống", stats.living ?? 0],
      ["mdi:candle", "Đã mất", stats.deceased ?? 0],
      ["mdi:layers-triple-outline", "Thế hệ", stats.levels ?? 0],
    ];
    return `<div class="print-summary">${items.map(([icon, label, value]) => `
      <div class="print-summary-item"><span class="print-summary-icon" aria-hidden="true">${this._printIcon(icon)}</span><span>${escapeHtml(label)}</span><strong>${Number(value) || 0}</strong></div>`).join("")}</div>`;
  }

  _exportTreeToPdf() {
    if (!this._tree) return;

    const printWindow = window.open("", "_blank");
    if (!printWindow) {
      this._showExportMessage("Trình duyệt đang chặn cửa sổ xuất PDF. Hãy cho phép cửa sổ bật lên rồi thử lại.", true);
      return;
    }

    const oldCollapsed = new Set(this._collapsedFamilies);
    const oldLayoutCache = this._layoutCache;
    const oldLayoutDirty = this._layoutDirty;
    const oldCollapseCache = this._collapseFamiliesCache;
    const oldInitialGenerationApplied = this._initialGenerationApplied;

    let layout;
    try {
      this._collapsedFamilies.clear();
      this._initialGenerationApplied = true;
      this._layoutDirty = true;
      this._collapseFamiliesCache = null;
      layout = this._getLayout();
    } finally {
      this._collapsedFamilies = oldCollapsed;
      this._layoutCache = oldLayoutCache;
      this._layoutDirty = oldLayoutDirty;
      this._collapseFamiliesCache = oldCollapseCache;
      this._initialGenerationApplied = oldInitialGenerationApplied;
    }

    if (!layout?.people?.length) {
      printWindow.close();
      this._showExportMessage("Không có dữ liệu cây gia phả để xuất.", true);
      return;
    }

    const config = this._config || DEFAULT_CONFIG;
    const title = config.title || this._tree?.title || "Cây Gia Phả";
    const scene = config.show_decorations ? this._decorativeScene(layout.width, layout.height) : "";
    const cardStyles = this._styles();
    const nodes = layout.people.map((person) => this._printPersonNode(person)).join("");
    const stats = this._tree?.stats || {};

    // Poster mode: the paper grows with the family tree instead of shrinking the tree to A0.
    // Text, frames and SVG connectors remain vector in the generated PDF. Only the original
    // portrait photos are raster, so their final sharpness depends on the source image size.
    const pxPerMm = 96 / 25.4;
    const mmPerPx = 1 / pxPerMm;
    const pageMarginMm = 18;
    const headingHeightPx = 150;
    const summaryHeightPx = 68;
    const treeGapPx = 24;
    const posterInfoHeightPx = 18;
    const treeTopPx = headingHeightPx + summaryHeightPx + posterInfoHeightPx + treeGapPx;

    // Keep the tree at 100% physical size. Increase the sheet dimensions as generations grow.
    // This avoids the quality loss/readability loss caused by fitting a very large tree onto A0.
    let printScale = 1;
    const naturalWidthMm = layout.width * mmPerPx + pageMarginMm * 2;
    const naturalHeightMm = (layout.height + treeTopPx) * mmPerPx + pageMarginMm * 2;

    // A0 is only the minimum canvas. The sheet expands beyond A0 when needed.
    const a0Landscape = { width: 1189, height: 841 };
    const a0Portrait = { width: 841, height: 1189 };
    const portraitTree = naturalHeightMm > naturalWidthMm;
    const minPage = portraitTree ? a0Portrait : a0Landscape;
    let pageWidthMm = Math.max(minPage.width, naturalWidthMm);
    let pageHeightMm = Math.max(minPage.height, naturalHeightMm);

    // Chromium has implementation limits for extremely large custom paper. Keep each side under
    // ~5 metres; only if the tree exceeds that extraordinary size do we apply one uniform scale.
    const maxPageSideMm = 5000;
    const maxContentWidthMm = maxPageSideMm - pageMarginMm * 2;
    const maxContentHeightMm = maxPageSideMm - pageMarginMm * 2 - treeTopPx * mmPerPx;
    const overflowScale = Math.min(
      1,
      maxContentWidthMm / Math.max(1, layout.width * mmPerPx),
      maxContentHeightMm / Math.max(1, layout.height * mmPerPx),
    );
    if (overflowScale < 1) {
      printScale = Math.max(0.1, overflowScale);
      pageWidthMm = Math.min(maxPageSideMm, Math.max(minPage.width, layout.width * printScale * mmPerPx + pageMarginMm * 2));
      pageHeightMm = Math.min(maxPageSideMm, Math.max(minPage.height, (layout.height * printScale + treeTopPx) * mmPerPx + pageMarginMm * 2));
    }

    pageWidthMm = Math.ceil(pageWidthMm);
    pageHeightMm = Math.ceil(pageHeightMm);
    const contentWidthPx = (pageWidthMm - pageMarginMm * 2) * pxPerMm;
    const contentHeightPx = (pageHeightMm - pageMarginMm * 2) * pxPerMm;
    const availableTreeHeightPx = Math.max(layout.height * printScale, contentHeightPx - treeTopPx);
    const scaledTreeWidth = layout.width * printScale;
    const scaledTreeHeight = layout.height * printScale;

    printWindow.document.open();
    printWindow.document.write(`<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>${escapeHtml(title)} - PDF Poster ${pageWidthMm}x${pageHeightMm}mm</title>
<style>
  @page { size: ${pageWidthMm}mm ${pageHeightMm}mm; margin: 0; }
  * { box-sizing:border-box; -webkit-print-color-adjust:exact !important; print-color-adjust:exact !important; }
  html, body { margin:0; padding:0; background:#fff; }
  body { font-family:${fontStack(config.content_font, "noto-sans")}; color:${safeColor(config.text_color, DEFAULT_CONFIG.text_color)}; }
  ${cardStyles}
  .print-sheet {
    position:relative;
    width:${pageWidthMm}mm;
    height:${pageHeightMm}mm;
    padding:${pageMarginMm}mm;
    overflow:hidden;
    background:${safeColor(config.background_color, DEFAULT_CONFIG.background_color)};
    --family-bg:${safeColor(config.background_color, DEFAULT_CONFIG.background_color)};
    --family-text:${safeColor(config.text_color, DEFAULT_CONFIG.text_color)};
    --family-muted:${safeColor(config.muted_text_color, DEFAULT_CONFIG.muted_text_color)};
    --family-line:${safeColor(config.line_color, DEFAULT_CONFIG.line_color)};
    --family-border:${safeColor(config.border_color, DEFAULT_CONFIG.border_color)};
    --family-male:${safeColor(config.male_color, DEFAULT_CONFIG.male_color)};
    --family-female:${safeColor(config.female_color, DEFAULT_CONFIG.female_color)};
    --family-other:${safeColor(config.other_color, DEFAULT_CONFIG.other_color)};
    --family-decoration:${safeColor(config.decoration_color, DEFAULT_CONFIG.decoration_color)};
    --family-title-font:${fontStack(config.title_font, "noto-serif")};
    --family-content-font:${fontStack(config.content_font, "noto-sans")};
  }
  .print-heading { height:${headingHeightPx}px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; }
  .print-heading h1 { margin:0; font-family:${fontStack(config.title_font, "noto-serif")}; font-size:${clampNumber(config.title_font_size, 20, 80, 46)}px; line-height:1.18; }
  .print-heading p { margin:10px 0 0; font-size:${clampNumber(config.subtitle_font_size, 10, 32, 14)}px; color:${safeColor(config.muted_text_color, DEFAULT_CONFIG.muted_text_color)}; }
  .print-summary { height:${summaryHeightPx}px; display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:9px; align-items:center; }
  .print-summary-item { min-width:0; display:flex; align-items:center; justify-content:center; gap:9px; padding:8px 12px; border:1px solid color-mix(in srgb,var(--family-border) 72%,transparent); border-radius:999px; background:rgba(255,255,255,.74); }
  .print-summary-item > span:not(.print-summary-icon) { color:var(--family-muted); font-size:11px; white-space:nowrap; }
  .print-summary-item strong { font-size:14px; }
  .print-summary-icon { width:16px; height:16px; display:inline-grid; place-items:center; flex:0 0 16px; color:var(--family-muted); opacity:.62; }
  .print-summary-icon .print-mdi-svg { width:16px !important; height:16px !important; display:block; fill:currentColor; }
  .print-poster-info { height:18px; display:flex; align-items:center; justify-content:center; color:var(--family-muted); font-size:10px; letter-spacing:.01em; }
  .print-tree-viewport { position:relative; width:100%; height:${availableTreeHeightPx}px; overflow:visible; }
  .print-tree-scale { position:absolute; left:50%; top:0; width:${layout.width}px; height:${layout.height}px; transform:translateX(-50%) scale(${printScale}); transform-origin:top center; }
  .print-tree { position:relative; width:${layout.width}px; height:${layout.height}px; }
  .tree-canvas { position:relative !important; inset:auto !important; transform:none !important; width:${layout.width}px !important; height:${layout.height}px !important; --branch-size:16px; --branch-border:1px; --branch-icon:10px; --branch-shadow-y:0px; --branch-shadow-blur:0px; }
  .branch-toggle, .zoom-controls, .fit-tree-button, .pdf-export-button, .header-actions, .detail-backdrop, .export-message { display:none !important; }
  .person-node { cursor:default !important; transition:none !important; filter:none !important; }
  .person-node:hover, .person-node:focus-visible { transform:none !important; filter:none !important; }
  .person-label { backdrop-filter:none !important; -webkit-backdrop-filter:none !important; box-shadow:0 1px 2px rgba(57,48,31,.08) !important; }
  .avatar-wrap { isolation:isolate; }
  .avatar-wrap img {
    display:block !important;
    width:100% !important;
    height:100% !important;
    border-radius:50% !important;
    clip-path:circle(50% at 50% 50%) !important;
    -webkit-clip-path:circle(50% at 50% 50%) !important;
    object-fit:cover !important;
    background:transparent !important;
  }
  .memorial ha-icon { display:none !important; }
  .memorial .print-candle-icon { width:21px; height:21px; display:grid; place-items:center; color:#fff9dc; filter:drop-shadow(0 1px 1px rgba(89,39,0,.45)); }
  .memorial .print-candle-icon .print-mdi-svg { width:21px !important; height:21px !important; display:block; fill:currentColor; }
  .print-icon-fallback { display:block; width:65%; height:65%; border-radius:50%; background:currentColor; opacity:.45; }
  .connectors { shape-rendering:geometricPrecision; text-rendering:geometricPrecision; }
  .decorative-scene { filter:none !important; }
  @media screen {
    body { background:#d7d7d7; padding:20px; }
    .print-sheet { margin:0 auto; box-shadow:0 4px 30px rgba(0,0,0,.22); }
  }
  @media print {
    html, body { width:${pageWidthMm}mm; height:${pageHeightMm}mm; overflow:hidden; }
    .print-sheet { box-shadow:none; }
  }
</style>
</head>
<body>
  <main class="print-sheet">
    <header class="print-heading">
      <h1>${escapeHtml(title)}</h1>
      ${config.subtitle ? `<p>${escapeHtml(config.subtitle)}</p>` : ""}
    </header>
    ${this._printSummary(stats)}
    <div class="print-poster-info">Khổ thiết kế: ${pageWidthMm} × ${pageHeightMm} mm · Tỷ lệ cây: ${Math.round(printScale * 100)}% · Nội dung vector</div>
    <section class="print-tree-viewport">
      <div class="print-tree-scale">
        <div class="print-tree">
          <div class="tree-canvas">
            ${scene}
            <svg class="connectors" viewBox="0 0 ${layout.width} ${layout.height}" preserveAspectRatio="none" aria-hidden="true">${layout.paths.join("")}</svg>
            ${nodes}
          </div>
        </div>
      </div>
    </section>
  </main>
<script>
  (() => {
    const replaceBrokenImage = (img) => {
      const fallback = img.dataset.fallbackSrc;
      if (fallback && img.src !== fallback) { img.src = fallback; return; }
      const text = img.dataset.fallback || '?';
      const div = document.createElement('div');
      div.className = img.dataset.fallbackClass || 'avatar-placeholder';
      div.textContent = text;
      img.replaceWith(div);
    };
    document.querySelectorAll('img').forEach((img) => img.addEventListener('error', () => replaceBrokenImage(img), {once:true}));
    const waitForImages = () => Promise.all(Array.from(document.images).map((img) => {
      if (img.complete) return img.decode?.().catch(() => {}) || Promise.resolve();
      return new Promise((resolve) => {
        img.addEventListener('load', () => { (img.decode?.().catch(() => {}) || Promise.resolve()).then(resolve); }, {once:true});
        img.addEventListener('error', resolve, {once:true});
      });
    }));
    const waitForFonts = document.fonts?.ready || Promise.resolve();
    Promise.all([waitForImages(), waitForFonts]).then(() => setTimeout(() => window.print(), 500));
  })();
<\/script>
</body>
</html>`);
    printWindow.document.close();
  }

  _showExportMessage(message, isError = false) {
    const existing = this.shadowRoot?.querySelector(".export-message");
    existing?.remove();
    const card = this.shadowRoot?.querySelector(".family-card");
    if (!card) return;
    card.insertAdjacentHTML("afterbegin", `<div class="export-message${isError ? " error" : ""}">${escapeHtml(message)}</div>`);
    window.setTimeout(() => this.shadowRoot?.querySelector(".export-message")?.remove(), 5000);
  }

  _formatDates(person) {
    const birth = formatPersonDate(person, "birth");
    const death = formatPersonDate(person, "death");
    const age = this._config.show_age ? calculateAgeText(person) : "";
    if (person.is_deceased) {
      const range = birth || death ? `${birth || "?"} – ${death || "?"}` : "";
      return [range, age].filter(Boolean).join(" · ");
    }
    return [birth ? `Sinh ${birth}` : "", age].filter(Boolean).join(" · ");
  }

  _cornerOrnament(side) {
    const transform = side === "right" ? 'transform="translate(74 0) scale(-1 1)"' : "";
    return `
      <svg class="corner-ornament ornament-${side}" viewBox="0 0 74 70" aria-hidden="true">
        <g ${transform}>
          <path d="M9 58 C11 37 21 16 43 10 C35 20 33 30 37 39 C43 53 58 51 65 35 C65 52 56 64 41 63 C30 63 22 55 22 45 C22 35 28 27 38 24 C27 26 18 36 18 49 C18 56 21 62 27 67"/>
          <path d="M23 31 C12 31 5 24 5 15 C14 20 22 18 27 10 C29 19 28 26 23 31 Z"/>
          <path d="M44 19 C49 7 59 4 68 8 C58 12 53 19 53 29 C49 27 46 23 44 19 Z"/>
          <circle cx="39" cy="42" r="3.5"/>
        </g>
      </svg>`;
  }

  _decorativeScene(width, height) {
    const baseY = Math.min(height - 36, Math.max(250, height * 0.62));
    const houseX = Math.max(18, width * 0.035);
    const treeX = Math.max(width * 0.67, width - 360);
    return `
      <svg class="decorative-scene" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
        <g class="scene-house" transform="translate(${round(houseX)} ${round(baseY - 190)})">
          <path d="M8 184 H310 M38 184 V105 L80 75 L119 106 V184 M119 184 V89 L181 47 L244 91 V184 M244 184 V112 L276 88 L302 112 V184"/>
          <path d="M25 105 L80 57 L129 105 M105 89 L181 28 L256 91 M237 112 L276 75 L314 113"/>
          <path d="M55 184 V132 H97 V184 M151 184 V112 H211 V184 M260 184 V133 H287 V184"/>
          <path d="M61 138 H90 M157 122 H205 M157 147 H205 M266 143 H282"/>
          <path d="M170 28 V4 L190 13 L170 20"/>
          <path d="M5 183 C25 167 42 170 54 184 M95 184 C111 164 131 165 145 184 M218 184 C234 163 257 168 269 184 M294 184 C306 168 318 171 329 184"/>
        </g>
        <g class="scene-tree" transform="translate(${round(treeX)} ${round(baseY - 210)})">
          <path d="M153 215 C151 176 163 151 181 126 C163 143 150 150 138 151 C152 126 160 104 162 79 C149 104 132 121 111 128 C123 107 129 88 127 68 C112 91 94 105 72 110 C82 88 82 68 76 51 C63 73 48 84 29 88 C42 67 48 49 45 31"/>
          <path d="M154 214 C172 179 186 157 205 143 C195 165 193 187 199 214"/>
          <path d="M155 214 C143 187 129 170 109 158 C123 178 127 197 125 214"/>
          <path d="M145 214 C149 186 150 151 148 117"/>
          <path d="M43 35 C16 28 7 49 22 62 C1 65 3 91 24 91 C12 108 31 127 48 114 C50 138 78 139 84 117 C98 134 123 122 117 101 C140 105 151 78 132 66 C145 47 123 25 104 39 C98 13 66 12 58 36 C53 34 48 34 43 35 Z"/>
          <path d="M164 39 C145 25 125 38 130 58 C108 59 105 87 126 93 C110 108 126 131 145 121 C148 143 176 145 183 124 C197 140 222 126 216 106 C239 107 247 80 228 69 C242 49 220 28 201 41 C194 18 166 18 158 40"/>
          <path d="M214 84 C229 70 252 79 251 100 C274 96 286 121 268 136 C286 148 277 175 255 172 C260 193 236 207 221 191 C210 209 182 202 179 181 C158 190 140 171 151 153 C132 142 140 115 162 115 C164 95 189 86 202 101 C204 94 208 88 214 84 Z"/>
        </g>
        <path class="scene-ground" d="M0 ${round(baseY)} C ${round(width * 0.2)} ${round(baseY - 12)}, ${round(width * 0.35)} ${round(baseY + 8)}, ${round(width * 0.5)} ${round(baseY)} S ${round(width * 0.82)} ${round(baseY - 8)}, ${width} ${round(baseY + 2)}"/>
      </svg>`;
  }

  _styles() {
    if (CARD_STYLES_CACHE) return CARD_STYLES_CACHE;
    CARD_STYLES_CACHE = `
      :host { display:block; min-width:0; }
      * { box-sizing:border-box; }
      .family-card {
        --family-bg:#fbfaf6;
        --family-text:#171512;
        --family-muted:#655f55;
        --family-line:#aaa493;
        --family-border:#d9d3c5;
        --family-male:#557d96;
        --family-female:#a97887;
        --family-other:#7d7294;
        --family-decoration:#d8d2c1;
        --family-radius:18px;
        --family-title-font:"Noto Serif", "DejaVu Serif", "Liberation Serif", serif;
        --family-content-font:"Noto Sans", "DejaVu Sans", "Liberation Sans", Arial, sans-serif;
        --family-title-size:46px;
        --family-subtitle-size:14px;
        position:relative;
        overflow:hidden;
        border-radius:var(--family-radius);
        color:var(--family-text);
        font-family:var(--family-content-font);
        background-color:var(--family-bg);
        background-image:var(--family-bg-image, linear-gradient(180deg, rgba(255,255,255,.98), rgba(249,247,240,.98)));
        background-size:cover;
        background-position:center;
        border:1px solid color-mix(in srgb, var(--family-border) 78%, transparent);
        box-shadow:0 12px 34px rgba(54,45,28,.08);
        isolation:isolate;
      }
      .paper-grain {
        position:absolute;
        inset:0;
        z-index:-1;
        opacity:.15;
        pointer-events:none;
        background-image:
          radial-gradient(circle at 18% 22%, rgba(95,82,55,.1) 0 0.6px, transparent .8px),
          radial-gradient(circle at 73% 68%, rgba(95,82,55,.08) 0 0.5px, transparent .75px);
        background-size:13px 13px, 17px 17px;
      }
      .family-header {
        position:relative;
        display:grid;
        grid-template-columns:74px minmax(0,1fr) 74px;
        align-items:start;
        min-height:112px;
        padding:20px 22px 6px;
      }
      .family-heading { text-align:center; padding:0 10px; }
      .family-heading h1 {
        margin:0;
        font-family:var(--family-title-font);
        font-size:clamp(20px, var(--family-title-size), 80px);
        line-height:1.12;
        letter-spacing:0;
        font-kerning:normal;
        text-rendering:optimizeLegibility;
        font-weight:600;
      }
      .family-heading p { margin:7px 0 0; color:var(--family-muted); font-size:var(--family-subtitle-size); letter-spacing:0; }
      .corner-ornament { width:74px; height:70px; fill:none; stroke:var(--family-decoration); stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round; opacity:.78; }
      .ornament-right { justify-self:end; }
      .header-actions { position:absolute; top:12px; right:14px; z-index:5; display:flex; align-items:center; gap:8px; }
      .zoom-controls {
        position:static;
        z-index:8;
        display:flex;
        border:1px solid color-mix(in srgb, var(--family-border) 78%, transparent);
        border-radius:999px;
        overflow:hidden;
        background:rgba(255,255,255,.84);
        box-shadow:0 4px 12px rgba(40,34,22,.06);
        backdrop-filter:blur(8px);
      }
      .zoom-controls button { width:34px; height:32px; padding:0; display:grid; place-items:center; border:0; border-right:1px solid color-mix(in srgb, var(--family-border) 62%, transparent); background:transparent; color:var(--family-text); cursor:pointer; }
      .zoom-controls button:last-child { border-right:0; }
      .zoom-controls button:hover { background:rgba(0,0,0,.045); }
      .zoom-controls ha-icon { --mdc-icon-size:18px; }
      .zoom-controls span { font-size:10px; min-width:34px; }
      .pdf-export-button { height:34px; padding:0 11px; display:flex; align-items:center; gap:6px; border:1px solid color-mix(in srgb, var(--family-border) 72%, transparent); border-radius:10px; background:color-mix(in srgb, var(--family-bg) 92%, white); color:var(--family-text); cursor:pointer; box-shadow:0 2px 8px rgba(0,0,0,.07); font:600 12px/1 var(--family-content-font); }
      .pdf-export-button:hover { background:color-mix(in srgb, var(--family-decoration) 10%, var(--family-bg)); }
      .pdf-export-button ha-icon { --mdc-icon-size:19px; color:#b3261e; }
      .export-message { position:absolute; top:10px; left:50%; transform:translateX(-50%); z-index:20; max-width:min(90%,560px); padding:10px 14px; border-radius:10px; background:#e8f5e9; color:#1b5e20; box-shadow:0 3px 15px rgba(0,0,0,.16); font:600 13px/1.4 var(--family-content-font); }
      .export-message.error { background:#ffebee; color:#b71c1c; }
      .summary { position:relative; z-index:3; display:grid; grid-template-columns:repeat(6,minmax(80px,1fr)); gap:7px; padding:4px 22px 12px; }
      .summary-item { display:grid; grid-template-columns:auto 1fr auto; align-items:center; gap:6px; padding:7px 9px; border:1px solid color-mix(in srgb, var(--family-border) 70%, transparent); border-radius:999px; background:rgba(255,255,255,.7); }
      .summary-item ha-icon { --mdc-icon-size:16px; opacity:.62; }
      .print-icon-cache { position:absolute !important; width:1px !important; height:1px !important; overflow:hidden !important; opacity:0 !important; pointer-events:none !important; left:-9999px !important; top:-9999px !important; }
      .summary-item span { color:var(--family-muted); font-size:10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .summary-item strong { font-size:13px; }
      .family-content { position:relative; min-height:280px; }
      .tree-scroll {
        overflow:auto;
        overscroll-behavior:contain;
        padding:0 10px 24px;
        scrollbar-width:thin;
        cursor:grab;
        touch-action:none;
        user-select:none;
        -webkit-user-select:none;
        -webkit-overflow-scrolling:touch;
      }
      .tree-scroll.is-panning { cursor:grabbing; }
      .tree-scroll.is-panning * { cursor:grabbing !important; }
      .scaled-stage { position:relative; margin:0 auto; }
      .tree-canvas { position:absolute; inset:0 auto auto 0; transform-origin:top left; }
      .decorative-scene { position:absolute; inset:0; width:100%; height:100%; z-index:0; overflow:visible; pointer-events:none; }
      .decorative-scene path { fill:none; stroke:var(--family-decoration); stroke-width:1.3; stroke-linecap:round; stroke-linejoin:round; vector-effect:non-scaling-stroke; }
      .decorative-scene .scene-house { opacity:.58; }
      .decorative-scene .scene-tree { opacity:.6; }
      .decorative-scene .scene-ground { opacity:.48; }
      .connectors { position:absolute; inset:0; width:100%; height:100%; z-index:1; overflow:visible; pointer-events:none; }
      .relation { fill:none; stroke:var(--family-line); stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round; opacity:.96; vector-effect:non-scaling-stroke; }
      .relation-spouse, .relation-parent-union { stroke-width:1.75; }
      .relation-adopted { stroke-dasharray:4 5; stroke-width:1.8; }
      .relation-stepchild { stroke-dasharray:8 4 2 4; stroke-width:1.9; }
      .relation-divorced { stroke-dasharray:7 5; opacity:.8; }
      .relation-explicit-sibling { stroke-dasharray:3 5; opacity:.65; }
      .branch-toggle {
        position:absolute;
        z-index:6;
        width:var(--branch-size, 32px);
        height:var(--branch-size, 32px);
        display:grid;
        place-items:center;
        padding:0;
        transform:translate(-50%, -50%);
        border:var(--branch-border, 2px) solid rgba(255,255,255,.96);
        border-radius:50%;
        background:color-mix(in srgb, var(--family-line) 88%, #5f594c);
        color:white;
        box-shadow:0 var(--branch-shadow-y, 3px) var(--branch-shadow-blur, 9px) rgba(44,37,25,.24);
        cursor:pointer;
      }
      .branch-toggle:hover, .branch-toggle:focus-visible { background:var(--family-text); outline:none; }
      .branch-toggle.is-collapsed { background:#a86a17; }
      .branch-toggle ha-icon { --mdc-icon-size:var(--branch-icon, 18px); }
      .person-node { position:absolute; z-index:2; cursor:pointer; outline:none; transition:transform .18s ease, filter .18s ease; }
      .person-node:hover, .person-node:focus-visible { transform:translateY(-3px); filter:drop-shadow(0 8px 10px rgba(47,39,25,.15)); }
      .person-label {
        box-sizing:border-box;
        position:absolute;
        left:0;
        top:var(--label-top);
        width:100%;
        min-height:var(--label-height);
        display:flex;
        flex-direction:column;
        align-items:center;
        justify-content:center;
        gap:2px;
        padding:9px 10px 8px;
        text-align:center;
        border:1.25px solid color-mix(in srgb, var(--family-border) 88%, #8c8678);
        border-radius:23px;
        background:rgba(255,255,255,.92);
        box-shadow:0 3px 8px rgba(57,48,31,.04);
        backdrop-filter:blur(4px);
      }
      .person-label strong { width:100%; font-family:var(--family-title-font); font-size:13px; line-height:1.2; font-weight:650; }
      .person-name { min-width:0; display:flex; align-items:baseline; justify-content:center; gap:3px; overflow:hidden; white-space:nowrap; }
      .person-name-full { display:block; overflow:hidden; text-overflow:ellipsis; }
      .person-name-prefix, .person-name-given { width:auto !important; color:inherit !important; font-family:inherit; line-height:inherit !important; white-space:nowrap; }
      .person-name-prefix { min-width:0; flex:1 1 auto; overflow:hidden; text-overflow:ellipsis; text-align:right; font-size:10.5px !important; font-weight:550; }
      .person-name-given { flex:0 0 auto; text-align:left; font-size:13px !important; font-weight:750; }
      .person-label span { width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--family-muted); font-size:9px; line-height:1.25; }
      .person-label small { width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:var(--family-muted); font-size:8.5px; line-height:1.25; opacity:.9; }
      .avatar-wrap {
        --accent:var(--family-other);
        box-sizing:border-box;
        position:absolute;
        z-index:2;
        top:0;
        left:50%;
        width:var(--avatar);
        height:var(--avatar);
        transform:translateX(-50%);
        border-radius:50%;
        padding:3px;
        background:#f7f4eb;
        border:1.5px solid color-mix(in srgb, var(--accent) 52%, var(--family-border));
        box-shadow:0 3px 9px rgba(49,41,27,.13);
      }
      .gender-male .avatar-wrap { --accent:var(--family-male); }
      .gender-female .avatar-wrap { --accent:var(--family-female); }
      .gender-other .avatar-wrap { --accent:var(--family-other); }
      .avatar-wrap img, .avatar-placeholder { width:100%; height:100%; display:grid; place-items:center; border-radius:50%; object-fit:cover; background:color-mix(in srgb, var(--accent) 10%, #f4f1e8); color:var(--accent); font-family:var(--family-title-font); font-size:calc(var(--avatar) * .28); font-weight:700; }
      .deceased .avatar-wrap img { filter:grayscale(1) contrast(.94); }
      .deceased { opacity:1; }
      .memorial, .adopted-mark, .stepchild-mark { position:absolute; bottom:-1px; display:grid; place-items:center; border-radius:50%; border:2px solid white; color:white; font-weight:700; box-shadow:0 2px 5px rgba(0,0,0,.13); }
      .memorial {
        right:-7px;
        bottom:-4px;
        width:32px;
        height:32px;
        background:linear-gradient(145deg, #f6b73c, #b95e0d);
        border-width:2.5px;
        color:#fff9dc;
        box-shadow:0 2px 8px rgba(155,76,5,.42), 0 0 0 2px rgba(246,183,60,.2);
      }
      .memorial ha-icon { --mdc-icon-size:21px; filter:drop-shadow(0 1px 1px rgba(89,39,0,.45)); }
      .adopted-mark { left:-2px; width:20px; height:20px; background:#7b735f; font-size:9px; }
      .stepchild-mark { left:-2px; width:20px; height:20px; background:#7c4d9b; font-size:9px; }
      .message { min-height:270px; display:flex; align-items:center; justify-content:center; gap:10px; padding:28px; text-align:center; color:var(--family-muted); }
      .message ha-icon { --mdc-icon-size:28px; }
      .message.error { color:var(--error-color,#c62828); }
      .spinner { width:24px; height:24px; border:3px solid color-mix(in srgb, var(--family-line) 35%, transparent); border-top-color:var(--family-line); border-radius:50%; animation:spin .8s linear infinite; }
      @keyframes spin { to { transform:rotate(360deg); } }
      .detail-backdrop { position:absolute; inset:0; z-index:30; display:flex; justify-content:flex-end; padding:14px; background:rgba(30,27,22,.26); backdrop-filter:blur(3px); }
      .detail-panel { position:relative; width:min(390px,100%); max-height:100%; overflow:auto; padding:22px; border:1px solid var(--family-border); border-radius:18px; background:rgba(255,255,255,.97); box-shadow:0 22px 60px rgba(30,25,17,.22); }
      .detail-close { position:absolute; top:10px; right:10px; width:34px; height:34px; display:grid; place-items:center; border:0; border-radius:50%; background:rgba(0,0,0,.05); color:var(--family-text); cursor:pointer; }
      .detail-hero { width:92px; height:92px; margin:4px auto 10px; padding:4px; border:1px solid var(--family-border); border-radius:50%; background:#f7f4eb; }
      .detail-hero img, .detail-placeholder { width:100%; height:100%; display:grid; place-items:center; border-radius:50%; object-fit:cover; background:#f0ede4; font-family:var(--family-title-font); font-size:26px; }
      .detail-panel h2 { margin:0; text-align:center; font-family:var(--family-title-font); font-size:22px; }
      .detail-role { margin:4px 0 16px; text-align:center; color:var(--family-muted); font-size:12px; }
      .detail-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
      .detail-grid div { min-width:0; padding:9px 10px; border:1px solid color-mix(in srgb, var(--family-border) 72%, transparent); border-radius:11px; background:#fbfaf6; }
      .detail-grid span { display:block; margin-bottom:3px; color:var(--family-muted); font-size:10px; }
      .detail-grid strong { display:block; overflow-wrap:anywhere; white-space:pre-line; font-size:12px; font-weight:600; }
      .detail-notes { margin-top:13px; padding:12px; border-radius:12px; background:#f7f4ec; }
      .detail-notes h3 { margin:0 0 5px; font-size:12px; }
      .detail-notes p { margin:0; color:var(--family-muted); font-size:12px; line-height:1.55; }
      @media (max-width:760px) {
        .family-header { grid-template-columns:52px minmax(0,1fr) 52px; min-height:96px; padding:16px 12px 4px; }
        .corner-ornament { width:52px; height:52px; }
        .family-heading h1 { font-size:min(var(--family-title-size), 36px); }
        .family-heading p { font-size:12px; }
        .summary { grid-template-columns:repeat(3,1fr); padding-inline:12px; }
        .header-actions { top:auto; right:10px; bottom:7px; }
        .zoom-controls { position:static; }
        .pdf-export-button span { display:none; }
        .pdf-export-button { width:34px; padding:0; justify-content:center; }
      }
      @media (max-width:520px) {
        .family-card { border-radius:calc(var(--family-radius) * .72); }
        .family-header { grid-template-columns:34px minmax(0,1fr) 34px; min-height:88px; padding:14px 8px 2px; }
        .corner-ornament { width:34px; height:42px; opacity:.55; }
        .family-heading { padding:0 4px; }
        .family-heading h1 { font-size:min(var(--family-title-size), 30px); }
        .family-heading p { margin-top:5px; font-size:11px; }
        .summary-item span { display:none; }
        .summary-item { grid-template-columns:auto 1fr; }
        .detail-grid { grid-template-columns:1fr; }
      }
    `;
    return CARD_STYLES_CACHE;
  }
}

class CayGiaPhaCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = { ...DEFAULT_CONFIG };
  }

  connectedCallback() {
    if (!this.shadowRoot?.childElementCount) this._render();
  }

  setConfig(config) {
    const cleaned = { ...(config || {}) };
    delete cleaned.entity;
    const nextConfig = { ...DEFAULT_CONFIG, ...cleaned };

    // Home Assistant can call setConfig again immediately after config-changed.
    // Avoid rebuilding the whole shadow DOM when values are unchanged, otherwise
    // the active input or switch is replaced and loses focus mid-interaction.
    if (sameCardConfig(this._config, nextConfig) && this.shadowRoot?.childElementCount) return;

    this._config = nextConfig;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    // The editor does not render state data. Re-rendering for every HA state update
    // makes focused fields flicker on busy installations, so only render once here.
    if (!this.shadowRoot?.childElementCount) this._render();
  }

  _render() {
    if (!this.shadowRoot) return;
    const c = this._config;
    const headingFields = [
      ["title", "Tiêu đề", "Ví dụ: Gia Phả Cụ Tiến Tiệp"],
      ["subtitle", "Nội dung mô tả", "Ví dụ: Theo dấu các thế hệ trong gia đình qua năm tháng."],
    ];
    const colorFields = [
      ["background_color", "Màu nền"],
      ["text_color", "Màu chữ"],
      ["muted_text_color", "Màu chữ phụ"],
      ["line_color", "Màu đường nối"],
      ["border_color", "Màu viền"],
      ["decoration_color", "Màu trang trí"],
      ["male_color", "Màu nam"],
      ["female_color", "Màu nữ"],
      ["other_color", "Màu giới tính khác"],
    ];
    const numberFields = [
      ["title_font_size", "Cỡ chữ tiêu đề", 20, 80],
      ["subtitle_font_size", "Cỡ chữ dòng mô tả", 10, 32],
      ["border_radius", "Bo góc thẻ", 0, 48],
      ["avatar_size", "Kích thước ảnh", 48, 120],
      ["node_width", "Chiều rộng ô tên", 118, 260],
      ["horizontal_spacing", "Khoảng cách ngang", 10, 160],
      ["vertical_spacing", "Khoảng cách dọc", 46, 190],
    ];
    const switches = [
      ["show_summary", "Hiện thống kê"],
      ["show_dates", "Hiện ngày sinh / mất"],
      ["show_age", "Hiện tuổi trên sơ đồ"],
      ["show_details", "Mở chi tiết khi chạm"],
      ["show_decorations", "Hiện nhà, cây và hoa văn"],
      ["deceased_grayscale", "Ảnh người đã mất dạng xám"],
      ["show_zoom", "Hiện nút thu phóng"],
    ];

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        .editor { display:grid; gap:16px; min-width:0; padding:12px 0 16px; }
        h3 { margin:6px 0 0; font-size:14px; }
        .grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:11px; }
        .full { grid-column:1 / -1; }
        .field-block { display:grid; gap:6px; min-width:0; }
        .field-label { color:var(--primary-text-color); font-size:12px; font-weight:500; }
        .native-field, .select-field select { box-sizing:border-box; width:100%; min-height:48px; padding:0 12px; color:var(--primary-text-color); background:var(--card-background-color); border:1px solid var(--divider-color); border-radius:8px; font:inherit; outline:none; }
        .native-field:focus, .select-field select:focus { border-color:var(--primary-color); box-shadow:0 0 0 1px var(--primary-color); }
        .native-field:disabled { opacity:.55; cursor:not-allowed; }
        .select-field { display:grid; gap:6px; font-size:12px; color:var(--secondary-text-color); }
        .hint { margin:0; color:var(--secondary-text-color); font-size:11px; line-height:1.45; }
        .color { display:grid; grid-template-columns:46px 1fr; align-items:center; gap:9px; min-height:44px; }
        .color input { width:42px; height:36px; padding:2px; border:1px solid var(--divider-color); border-radius:8px; background:transparent; }
        .color span, .switch { font-size:13px; }
        .switch { display:flex; justify-content:space-between; align-items:center; min-height:40px; gap:12px; }
        @media(max-width:520px) { .grid { grid-template-columns:1fr; } .full { grid-column:auto; } }
      </style>
      <div class="editor">
        <h3>Tiêu đề và phông chữ</h3>
        <div class="grid">
          ${headingFields.map(([key, label, hint]) => `<label class="field-block full"><span class="field-label">${escapeHtml(label)}</span><input class="native-field text-field" data-key="${key}" type="text" value="${escapeAttr(c[key] ?? "")}" placeholder="${escapeAttr(hint.replace(/^Ví dụ:\s*/, ""))}"><span class="hint">${escapeHtml(hint)}</span></label>`).join("")}
          <label class="select-field">Phông chữ tiêu đề và họ tên
            <select id="title-font">
              ${FONT_OPTIONS.map((font) => `<option value="${font.value}" ${font.value === c.title_font ? "selected" : ""}>${escapeHtml(font.label)}</option>`).join("")}
            </select>
            <span class="hint">Áp dụng cho tiêu đề thẻ, họ tên từng người và tên trong bảng chi tiết.</span>
          </label>
          <label class="select-field">Phông chữ nội dung khác
            <select id="content-font">
              ${FONT_OPTIONS.map((font) => `<option value="${font.value}" ${font.value === c.content_font ? "selected" : ""}>${escapeHtml(font.label)}</option>`).join("")}
            </select>
            <span class="hint">Áp dụng cho mô tả, ngày tháng, thống kê, ghi chú và các nội dung phụ.</span>
          </label>
          <label class="field-block full">
            <span class="field-label">URL hình nền</span>
            <input class="native-field text-field" data-key="background_image" type="text" value="${escapeAttr(c.background_image ?? "")}" placeholder="/local/hinh-nen-gia-pha.jpg">
            <span class="hint">Có thể để trống để dùng nền giấy mặc định của thẻ.</span>
          </label>
        </div>
        <h3>Màu sắc</h3>
        <div class="grid">
          ${colorFields.map(([key, label]) => `<label class="color"><input type="color" data-key="${key}" value="${escapeAttr(hexColor(c[key], DEFAULT_CONFIG[key]))}"><span>${label}</span></label>`).join("")}
        </div>
        <h3>Kích thước và khoảng cách</h3>
        <div class="grid">
          ${numberFields.map(([key, label, min, max]) => `<label class="field-block"><span class="field-label">${escapeHtml(label)}</span><input class="native-field number-field" data-key="${key}" type="number" min="${min}" max="${max}" value="${escapeAttr(c[key])}"></label>`).join("")}
        </div>
        <h3>Hiển thị ban đầu</h3>
        <div class="grid">
          <label class="field-block full">
            <span class="field-label">Mức thu phóng khi mở thẻ (%)</span>
            <input class="native-field number-field" data-key="initial_zoom" type="number" min="50" max="160" step="10" inputmode="numeric" value="${escapeAttr(clampNumber(c.initial_zoom, 50, 160, 50))}">
            <span class="hint">Chọn từ 50% đến 160%. Nút phần trăm trên thẻ sẽ đưa sơ đồ trở về đúng mức mặc định này.</span>
          </label>
          <label class="switch full"><span>Giới hạn số thế hệ khi mở thẻ</span><ha-switch data-key="limit_initial_generations" ${c.limit_initial_generations ? "checked" : ""}></ha-switch></label>
          <label class="field-block full">
            <span class="field-label">Số thế hệ hiển thị ban đầu</span>
            <input id="initial-generation-limit" class="native-field number-field" data-key="initial_generation_limit" type="number" min="1" max="50" step="1" inputmode="numeric" value="${escapeAttr(clampNumber(c.initial_generation_limit, 1, 50, 3))}" ${c.limit_initial_generations ? "" : "disabled"}>
            <span class="hint">Ví dụ nhập 3: khi mở thẻ chỉ hiện đến thế hệ thứ 3. Các nhánh đời sau được thu gọn và có thể mở lại bằng nút dấu cộng trên sơ đồ.</span>
          </label>
        </div>
        <h3>Nội dung</h3>
        <div class="grid">
          ${switches.map(([key, label]) => `<label class="switch"><span>${label}</span><ha-switch data-key="${key}" ${c[key] ? "checked" : ""}></ha-switch></label>`).join("")}
        </div>
      </div>
    `;

    this.shadowRoot.querySelector("#title-font")?.addEventListener("change", (event) => {
      this._setValue("title_font", event.target.value);
    });
    this.shadowRoot.querySelector("#content-font")?.addEventListener("change", (event) => {
      this._setValue("content_font", event.target.value);
    });
    this.shadowRoot.querySelectorAll(".text-field").forEach((field) => {
      field.addEventListener("change", (event) => this._setValue(field.dataset.key, event.target.value));
    });
    this.shadowRoot.querySelectorAll(".number-field").forEach((field) => {
      field.addEventListener("change", (event) => {
        const minimum = Number(event.target.min);
        const maximum = Number(event.target.max);
        const fallback = DEFAULT_CONFIG[field.dataset.key] ?? minimum;
        const value = Math.round(clampNumber(event.target.value, minimum, maximum, fallback));
        event.target.value = String(value);
        this._setValue(field.dataset.key, value);
      });
    });
    this.shadowRoot.querySelectorAll('input[type="color"]').forEach((field) => {
      field.addEventListener("input", (event) => this._setValue(field.dataset.key, event.target.value));
    });
    this.shadowRoot.querySelectorAll("ha-switch").forEach((field) => {
      field.addEventListener("change", () => {
        this._setValue(field.dataset.key, field.checked);
        if (field.dataset.key === "limit_initial_generations") {
          const generationField = this.shadowRoot.querySelector("#initial-generation-limit");
          if (generationField) generationField.disabled = !field.checked;
        }
      });
    });
  }

  _setValue(key, value) {
    const next = { ...this._config };
    if (value === undefined || value === "") delete next[key];
    else next[key] = value;
    this._config = next;
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config: next },
      bubbles: true,
      composed: true,
    }));
  }
}

async function loadFamilyTree(hass, entryId, revision) {
  const key = `${entryId}:${revision}`;
  for (const cachedKey of FAMILY_TREE_CACHE.keys()) {
    if (cachedKey !== key && cachedKey.startsWith(`${entryId}:`)) {
      FAMILY_TREE_CACHE.delete(cachedKey);
    }
  }
  const cached = FAMILY_TREE_CACHE.get(key);
  if (cached?.tree && Date.now() - cached.loadedAt < TREE_CACHE_MAX_AGE) {
    return cached.tree;
  }
  if (cached?.promise) return cached.promise;

  const promise = hass.callWS({
    type: "cay_gia_pha/get_tree",
    entry_id: entryId,
  }).then((tree) => {
    FAMILY_TREE_CACHE.set(key, { tree, loadedAt: Date.now() });
    return tree;
  }).catch((error) => {
    if (FAMILY_TREE_CACHE.get(key)?.promise === promise) FAMILY_TREE_CACHE.delete(key);
    throw error;
  });

  FAMILY_TREE_CACHE.set(key, { promise, loadedAt: Date.now() });
  return promise;
}

function sameCardConfig(left, right) {
  if (left === right) return true;
  if (!left || !right) return false;
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(right).sort();
  if (leftKeys.length !== rightKeys.length) return false;
  return leftKeys.every((key, index) => key === rightKeys[index] && left[key] === right[key]);
}

function chooseFamilyAnchor(members, maps) {
  return [...members].sort((a, b) => {
    const parentDiff = Number(Boolean(parentKey(b))) - Number(Boolean(parentKey(a)));
    if (parentDiff) return parentDiff;
    const siblingDiff = (maps.siblings.get(b.person_id)?.size || 0) - (maps.siblings.get(a.person_id)?.size || 0);
    if (siblingDiff) return siblingDiff;
    return familyPersonSort(a, b);
  })[0];
}

function uniqueStrings(value) {
  const values = Array.isArray(value) ? value : (value ? [value] : []);
  return [...new Set(values.map((item) => String(item || "").trim()).filter(Boolean))];
}

function parentKey(person) {
  const father = person?.father_id ? String(person.father_id) : "";
  const mother = person?.mother_id ? String(person.mother_id) : "";
  return father || mother ? `parents:${father}|${mother}` : null;
}

function familyBranchKey(parentIds) {
  return `family:${uniqueStrings(parentIds).sort().join("|")}`;
}

function pairKey(a, b) {
  return [String(a), String(b)].sort().join("|");
}

function orderCouple(a, b) {
  if (a.gender === "male" && b.gender === "female") return [a, b];
  if (a.gender === "female" && b.gender === "male") return [b, a];
  return familyPersonSort(a, b) <= 0 ? [a, b] : [b, a];
}

function chooseSpouseHub(members, maps) {
  if (!members.length) return null;
  const memberIds = new Set(members.map((member) => member.person_id));
  return [...members].sort((a, b) => {
    const aCount = [...(maps.spouses.get(a.person_id) || [])].filter((id) => memberIds.has(id)).length;
    const bCount = [...(maps.spouses.get(b.person_id) || [])].filter((id) => memberIds.has(id)).length;
    const parentDiff = Number(Boolean(parentKey(b))) - Number(Boolean(parentKey(a)));
    return bCount - aCount || parentDiff || familyPersonSort(a, b);
  })[0];
}

function orderSpouseGroup(members, maps) {
  if (members.length < 2) return [...members];
  const hub = chooseSpouseHub(members, maps);
  if (!hub) return [...members].sort(familyPersonSort);

  const spouses = members
    .filter((member) => maps.spouses.get(hub.person_id)?.has(member.person_id))
    .sort((a, b) => {
      const aRank = maps.spouseRanks.get(pairKey(hub.person_id, a.person_id)) || a.spouse_order || 999;
      const bRank = maps.spouseRanks.get(pairKey(hub.person_id, b.person_id)) || b.spouse_order || 999;
      return aRank - bRank || familyPersonSort(a, b);
    });
  const orderedIds = new Set([hub.person_id, ...spouses.map((spouse) => spouse.person_id)]);
  const others = members.filter((member) => !orderedIds.has(member.person_id)).sort(familyPersonSort);

  if (spouses.length === 1) {
    return [...orderCouple(hub, spouses[0]), ...others];
  }

  const left = spouses.filter((_, index) => index % 2 === 0).reverse();
  const right = spouses.filter((_, index) => index % 2 === 1);
  return [...left, hub, ...right, ...others];
}

function marriageSourceX(parents, coupleGap) {
  if (!parents.length) return 0;
  if (parents.length === 1) return parents[0].x + parents[0].nodeWidth / 2;
  const male = parents.find((parent) => parent.gender === "male");
  const female = parents.find((parent) => parent.gender === "female");
  if (male && female) {
    return male.x <= female.x
      ? female.x - coupleGap / 2
      : female.x + female.nodeWidth + coupleGap / 2;
  }
  const centers = parents.map((parent) => parent.x + parent.nodeWidth / 2);
  return centers.reduce((sum, value) => sum + value, 0) / centers.length;
}

function marriageSourceY(parents) {
  return Math.max(...parents.map((parent) => (
    parent.y + parent.labelTop + parent.labelHeight * 0.48
  )));
}

function wifeRankLabel(rank, wifeCount = 1) {
  const count = Math.max(1, Number(wifeCount) || 1);
  if (count === 1) return "Vợ";
  const value = Math.max(1, Number(rank) || 1);
  return value === 1 ? "Vợ cả" : `Vợ ${value}`;
}

function familyPersonSort(a, b) {
  const aOrder = Number(a?.birth_order) > 0 ? Number(a.birth_order) : Number.POSITIVE_INFINITY;
  const bOrder = Number(b?.birth_order) > 0 ? Number(b.birth_order) : Number.POSITIVE_INFINITY;
  if (aOrder !== bOrder) return aOrder - bOrder;
  const aBirth = partialDateSortKey(a, "birth");
  const bBirth = partialDateSortKey(b, "birth");
  for (let index = 0; index < aBirth.length; index += 1) {
    if (aBirth[index] !== bBirth[index]) return aBirth[index] - bBirth[index];
  }
  const sort = (Number(a?.sort_order) || 0) - (Number(b?.sort_order) || 0);
  if (sort) return sort;
  return String(a?.full_name || "").localeCompare(String(b?.full_name || ""), "vi");
}

function defaultAvatarUrl(gender) {
  return DEFAULT_AVATAR_URLS[gender] || DEFAULT_AVATAR_URLS.other;
}

function personNameMarkup(name) {
  const text = String(name || "Không rõ tên").normalize("NFC").trim() || "Không rõ tên";
  const parts = text.split(/\s+/).filter(Boolean);
  if (text.length <= 18 || parts.length < 3) {
    return `<strong class="person-name person-name-full">${escapeHtml(text)}</strong>`;
  }
  const givenName = parts.pop();
  return `<strong class="person-name" title="${escapeAttr(text)}"><span class="person-name-prefix">${escapeHtml(parts.join(" "))}</span><span class="person-name-given">${escapeHtml(givenName)}</span></strong>`;
}

function initials(name) {
  return String(name || "?")
    .normalize("NFC")
    .trim()
    .split(/\s+/)
    .slice(-2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("") || "?";
}

function partialDateParts(person, prefix) {
  const direct = [
    optionalInteger(person?.[`${prefix}_year`]),
    optionalInteger(person?.[`${prefix}_month`]),
    optionalInteger(person?.[`${prefix}_day`]),
  ];
  if (direct.some((value) => value !== null)) return direct;
  return parsePartialDateString(person?.[`${prefix}_date`]);
}

function parsePartialDateString(value) {
  const text = String(value || "").trim();
  let match = /^(\d{1,4})-(\d{1,2})-(\d{1,2})$/.exec(text);
  if (match) return match.slice(1).map((part) => Number(part));
  match = /^(\d{1,4})-(\d{1,2})$/.exec(text);
  if (match) return [Number(match[1]), Number(match[2]), null];
  match = /^(\d{1,4})$/.exec(text);
  if (match) return [Number(match[1]), null, null];
  match = /^--(\d{1,2})-(\d{1,2})$/.exec(text);
  if (match) return [null, Number(match[1]), Number(match[2])];
  match = /^--(\d{1,2})$/.exec(text);
  if (match) return [null, Number(match[1]), null];
  match = /^---(\d{1,2})$/.exec(text);
  if (match) return [null, null, Number(match[1])];
  match = /^(\d{1,4})---(\d{1,2})$/.exec(text);
  if (match) return [Number(match[1]), null, Number(match[2])];
  return [null, null, null];
}

function formatPersonDate(person, prefix) {
  const [year, month, day] = partialDateParts(person, prefix);
  if (year === null && month === null && day === null) return "";
  if (year !== null && month !== null && day !== null) return `${pad2(day)}/${pad2(month)}/${year}`;
  if (year !== null && month !== null) return `${pad2(month)}/${year}`;
  if (year !== null && day !== null) return `Ngày ${pad2(day)}, năm ${year}`;
  if (year !== null) return String(year);
  if (month !== null && day !== null) return `${pad2(day)}/${pad2(month)}`;
  if (month !== null) return `Tháng ${pad2(month)}`;
  return `Ngày ${pad2(day)}`;
}

function calculateAgeText(person) {
  const age = calculateAge(person);
  return age === null ? "Không rõ" : `${age} tuổi`;
}

function calculateAge(person) {
  const [birthYear, birthMonth, birthDay] = partialDateParts(person, "birth");
  if (birthYear === null) return null;
  let referenceYear;
  let referenceMonth;
  let referenceDay;
  if (person?.is_deceased) {
    [referenceYear, referenceMonth, referenceDay] = partialDateParts(person, "death");
    if (referenceYear === null) return null;
  } else {
    const now = new Date();
    referenceYear = now.getFullYear();
    referenceMonth = now.getMonth() + 1;
    referenceDay = now.getDate();
  }
  let age = referenceYear - birthYear;
  if (!Number.isFinite(age) || age < 0) return null;
  if (
    birthMonth !== null && birthDay !== null &&
    referenceMonth !== null && referenceDay !== null &&
    (referenceMonth < birthMonth || (referenceMonth === birthMonth && referenceDay < birthDay))
  ) {
    age -= 1;
  }
  return age >= 0 ? age : null;
}

function partialDateSortKey(person, prefix) {
  const [year, month, day] = partialDateParts(person, prefix);
  return [year ?? 9999, month ?? 13, day ?? 32];
}

function optionalInteger(value) {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const number = Number(value);
  return Number.isInteger(number) ? number : null;
}

function pad2(value) {
  return String(value ?? "").padStart(2, "0");
}

function clampNumber(value, min, max, fallback) {
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return Math.min(max, Math.max(min, number));
}

function round(value) {
  return Math.round(Number(value) * 10) / 10;
}

function fontStack(value, fallbackValue) {
  // Cấu hình cũ dùng Georgia được chuyển sang bộ serif có fallback tiếng Việt tốt hơn.
  const normalized = value === "georgia" || value === "garamond" ? "noto-serif" : value;
  return (
    FONT_OPTIONS.find((font) => font.value === normalized)?.stack ||
    FONT_OPTIONS.find((font) => font.value === fallbackValue)?.stack ||
    FONT_OPTIONS[0].stack
  );
}

function safeColor(value, fallback) {
  const text = String(value || "").trim();
  return /^(#[0-9a-f]{3,8}|rgba?\([\d\s.,%]+\)|hsla?\([\d\s.,%deg]+\)|[a-z]+)$/i.test(text) ? text : fallback;
}

function hexColor(value, fallback) {
  const text = String(value || "").trim();
  return /^#[0-9a-f]{6}$/i.test(text) ? text : fallback;
}

function cssUrl(value) {
  return String(value || "").replace(/["'\\\n\r()]/g, (char) => encodeURIComponent(char));
}

function escapeHtml(value) {
  return String(value ?? "")
    .normalize("NFC")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function installFamilyTreeImagePreviewEnhancer() {
  customElements.whenDefined("ha-selector-file").then(() => {
    const FileSelector = customElements.get("ha-selector-file");
    if (!FileSelector || FileSelector.prototype.__cgpImagePreviewEnhanced) return;

    Object.defineProperty(FileSelector.prototype, "__cgpImagePreviewEnhanced", {
      value: true,
      configurable: false,
      enumerable: false,
    });

    const originalConnected = FileSelector.prototype.connectedCallback;
    const originalDisconnected = FileSelector.prototype.disconnectedCallback;

    FileSelector.prototype.connectedCallback = function (...args) {
      originalConnected?.apply(this, args);
      queueMicrotask(() => setupImagePreview(this));
    };

    FileSelector.prototype.disconnectedCallback = function (...args) {
      clearImagePreview(this);
      this.__cgpPreviewObserver?.disconnect();
      this.__cgpPreviewObserver = null;
      originalDisconnected?.apply(this, args);
    };

    function isFamilyTreeImageField(host) {
      const accept = String(host.selector?.file?.accept || "").toLowerCase();
      const label = String(host.label || "").normalize("NFC").toLowerCase();
      if (!accept.includes("image/")) return false;
      return (
        label.includes("ảnh hiển thị") ||
        label.includes("ảnh đại diện") ||
        label.includes("display image") ||
        label.includes("portrait")
      );
    }

    function setupImagePreview(host, attempt = 0) {
      if (!host.isConnected) return;
      if (!host.shadowRoot) {
        if (attempt < 12) setTimeout(() => setupImagePreview(host, attempt + 1), 50);
        return;
      }
      if (!isFamilyTreeImageField(host)) {
        // Do not keep scheduling work for unrelated file selectors across Home
        // Assistant. Retry only while the selector metadata has not arrived yet.
        if ((!host.selector || host.label === undefined) && attempt < 12) {
          setTimeout(() => setupImagePreview(host, attempt + 1), 50);
        }
        return;
      }

      if (!host.__cgpPreviewObserver) {
        host.__cgpPreviewObserver = new MutationObserver(() => wireImageUploader(host));
        host.__cgpPreviewObserver.observe(host.shadowRoot, { childList: true, subtree: true });
      }
      if (!host.__cgpPreviewValueWired) {
        host.__cgpPreviewValueWired = true;
        host.addEventListener("value-changed", (event) => {
          if (!event.detail?.value) clearImagePreview(host);
        });
      }
      wireImageUploader(host);
    }

    function wireImageUploader(host) {
      const uploader = host.shadowRoot?.querySelector("ha-file-upload");
      if (uploader && !uploader.__cgpPreviewWired) {
        uploader.__cgpPreviewWired = true;
        uploader.addEventListener("file-picked", (event) => {
          const file = event.detail?.files?.[0];
          if (!(file instanceof File)) return;
          if (host.__cgpPreviewUrl) URL.revokeObjectURL(host.__cgpPreviewUrl);
          host.__cgpPreviewUrl = URL.createObjectURL(file);
          host.__cgpPreviewName = file.name;
          renderImagePreview(host);
        });
        uploader.addEventListener("change", () => {
          setTimeout(() => {
            if (!host.value) clearImagePreview(host);
          }, 0);
        });
      }
      renderImagePreview(host);
    }

    function renderImagePreview(host) {
      const root = host.shadowRoot;
      if (!root) return;
      let preview = root.querySelector("[data-cgp-image-preview]");
      if (!host.__cgpPreviewUrl) {
        preview?.remove();
        return;
      }
      if (!preview) {
        preview = document.createElement("div");
        preview.dataset.cgpImagePreview = "";
        Object.assign(preview.style, {
          display: "grid",
          gridTemplateColumns: "72px minmax(0, 1fr)",
          alignItems: "center",
          gap: "12px",
          marginTop: "10px",
          padding: "10px",
          border: "1px solid var(--divider-color)",
          borderRadius: "12px",
          background: "var(--card-background-color)",
        });
        const image = document.createElement("img");
        image.alt = "Xem trước ảnh đại diện";
        Object.assign(image.style, {
          width: "72px",
          height: "72px",
          objectFit: "cover",
          borderRadius: "50%",
          border: "1px solid var(--divider-color)",
        });
        const text = document.createElement("div");
        text.innerHTML = '<strong style="display:block;font-size:13px">Xem trước ảnh đã chọn</strong><span style="display:block;margin-top:4px;color:var(--secondary-text-color);font-size:12px;overflow-wrap:anywhere"></span>';
        preview.append(image, text);
        root.append(preview);
      }
      const image = preview.querySelector("img");
      const filename = preview.querySelector("span");
      if (image && image.src !== host.__cgpPreviewUrl) image.src = host.__cgpPreviewUrl;
      const displayName = host.__cgpPreviewName || "Ảnh đại diện";
      if (filename && filename.textContent !== displayName) filename.textContent = displayName;
    }

    function clearImagePreview(host) {
      if (host.__cgpPreviewUrl) URL.revokeObjectURL(host.__cgpPreviewUrl);
      host.__cgpPreviewUrl = null;
      host.__cgpPreviewName = null;
      host.shadowRoot?.querySelector("[data-cgp-image-preview]")?.remove();
    }
  }).catch(() => undefined);
}

if (!customElements.get("cay-gia-pha-card")) {
  customElements.define("cay-gia-pha-card", CayGiaPhaCard);
}
if (!customElements.get("cay-gia-pha-card-editor")) {
  customElements.define("cay-gia-pha-card-editor", CayGiaPhaCardEditor);
}

installFamilyTreeImagePreviewEnhancer();

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "cay-gia-pha-card")) {
  window.customCards.push({
    type: "cay-gia-pha-card",
    name: "Cây Gia Phả",
    preview: true,
    description: "Sơ đồ cây gia phả nhiều thế hệ với ảnh chân dung và quan hệ gia đình.",
    getEntitySuggestion: (hass, entityId) => {
      const state = hass?.states?.[entityId];
      if (state?.attributes?.integration !== "cay_gia_pha") return null;
      return { config: { type: "custom:cay-gia-pha-card" } };
    },
  });
}

console.info(`%c CÂY GIA PHẢ %c ${RESOURCE_VERSION ? `v${RESOURCE_VERSION}` : ""} `, "color:white;background:#655f55;font-weight:700;padding:2px 6px;border-radius:4px 0 0 4px", "color:#655f55;background:#eeeae0;padding:2px 6px;border-radius:0 4px 4px 0");
