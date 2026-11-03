(() => {
    "use strict";

    const HEX = /^#[0-9a-f]{6}$/i;
    const SWIPE_THRESHOLD = 90;
    const KEYS = { arrowleft: "no", n: "no", arrowright: "yes", y: "yes", s: "skip", arrowdown: "skip" };

    const root = document.documentElement;
    const $ = (sel, el = document) => el.querySelector(sel);
    const card = $("#card");
    const stats = $("#stats");
    const toastEl = $("#toast");
    const dialog = $("#restore");
    const form = $("#restore-form");
    const input = $("#restore-input");
    const preview = $("#restore-preview");
    const hint = $("#restore-hint");
    const themeColor = $('meta[name="theme-color"]');
    const favicon = $('link[rel="icon"]');

    let nextCard = null;
    let busy = false;
    let statsSeq = 0;
    let suppressClick = false;

    // --- Shades -------------------------------------------------------------

    const getText = async (url, init) => {
        const res = await fetch(url, init);
        if (!res.ok) throw new Error(`${url}: ${res.status}`);
        return res.text();
    };

    const prefetch = () => {
        const p = getText("/next-shade");
        p.catch(() => {
            if (nextCard === p) nextCard = null;
        });
        nextCard = p;
    };

    const swatch = () => $(".swatch", card);

    const applyShade = (el) => {
        if (!el) return;
        root.style.setProperty("--shade", el.dataset.shade);
        root.style.setProperty("--ink", el.dataset.ink);
        themeColor.content = el.dataset.shade;
    };

    async function showNext() {
        const pending = nextCard || getText("/next-shade");
        nextCard = null;
        card.innerHTML = await pending;
        applyShade(swatch());
        prefetch();
    }

    const refreshFavicon = () => {
        favicon.href = `/favicon.ico?v=${Date.now()}`;
    };

    async function vote(value) {
        const el = swatch();
        if (!el || busy) return;
        busy = true;

        const body = new URLSearchParams({ shade: el.dataset.shade, vote: value });
        const seq = ++statsSeq;
        const saved = getText("/vote", { method: "POST", body }).then((html) => {
            if (seq !== statsSeq) return;
            stats.innerHTML = html;
            refreshFavicon();
        });

        try {
            await showNext();
        } catch {
            toast("Couldn't load the next shade");
        } finally {
            busy = false;
        }
        saved.catch(() => toast("Your vote couldn't be saved"));
    }

    // --- Copy & toast -------------------------------------------------------

    let toastTimer;
    function toast(message, color) {
        toastEl.replaceChildren();
        if (color) {
            const dot = document.createElement("span");
            dot.className = "toast-dot";
            dot.style.background = color;
            toastEl.append(dot);
        }
        toastEl.append(message);
        toastEl.classList.add("show");
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toastEl.classList.remove("show"), 2200);
    }

    async function copy(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch {
            const ta = document.createElement("textarea");
            ta.value = text;
            ta.setAttribute("readonly", "");
            ta.style.cssText = "position:fixed;opacity:0";
            document.body.append(ta);
            ta.select();
            const ok = document.execCommand("copy");
            ta.remove();
            return ok;
        }
    }

    // --- Restore dialog -----------------------------------------------------

    const normalize = (value) => {
        const v = value.trim().toLowerCase();
        return v && !v.startsWith("#") ? `#${v}` : v;
    };

    function updatePreview() {
        const v = normalize(input.value);
        const valid = HEX.test(v);
        preview.style.background = valid ? v : "";
        input.setAttribute("aria-invalid", String(!valid && v.length >= 7));
        hint.textContent = "";
    }

    function openRestore() {
        input.value = $("[data-user-color]", stats)?.dataset.userColor || "";
        updatePreview();
        dialog.showModal();
        input.select();
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const value = normalize(input.value);
        if (!HEX.test(value)) {
            hint.textContent = "Enter a 6-digit hex color like #1a2b3c";
            input.focus();
            return;
        }
        const body = new URLSearchParams({ base_color: value });
        try {
            const res = await fetch("/load-base-color", { method: "POST", body });
            const data = await res.json();
            if (!data.success) {
                hint.textContent = res.status === 404 ? "No session uses this color yet" : data.error;
                return;
            }
            dialog.close();
            statsSeq++;
            stats.innerHTML = await getText("/stats");
            refreshFavicon();
            toast("Welcome back!", value);
        } catch {
            hint.textContent = "Network error. Please try again.";
        }
    });

    input.addEventListener("input", updatePreview);
    dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close();
    });

    // --- Events -------------------------------------------------------------

    document.addEventListener(
        "click",
        (event) => {
            if (suppressClick) {
                event.stopPropagation();
                event.preventDefault();
                suppressClick = false;
            }
        },
        true,
    );

    document.addEventListener("click", async (event) => {
        const target = event.target.closest("[data-vote],[data-action],[data-copy-text]");
        if (!target) return;
        const { vote: voteValue, action, copyText } = target.dataset;

        if (voteValue) return vote(voteValue);
        if (action === "restore") return openRestore();
        if (action === "close") return dialog.close();
        if (copyText) {
            const isHex = HEX.test(copyText);
            if (await copy(copyText)) toast(`Copied ${copyText}`, isHex ? copyText : null);
            else toast("Couldn't copy to clipboard");
        }
    });

    document.addEventListener("keydown", (event) => {
        if (dialog.open || event.metaKey || event.ctrlKey || event.altKey) return;
        if (event.target.closest("input, textarea")) return;
        const value = KEYS[event.key.toLowerCase()];
        if (!value) return;
        event.preventDefault();
        const button = $(`.actions [data-vote="${value}"]`);
        if (button) {
            button.classList.add("is-pressed");
            setTimeout(() => button.classList.remove("is-pressed"), 120);
        }
        vote(value);
    });

    // --- Swipe --------------------------------------------------------------

    let drag = null;

    card.addEventListener("pointerdown", (event) => {
        const el = event.target.closest(".swatch");
        if (!el || event.button !== 0 || busy) return;
        drag = { el, id: event.pointerId, x: event.clientX, y: event.clientY, dx: 0, active: false };
    });

    card.addEventListener("pointermove", (event) => {
        if (!drag || event.pointerId !== drag.id) return;
        const dx = event.clientX - drag.x;
        const dy = event.clientY - drag.y;
        if (!drag.active) {
            if (Math.abs(dx) < 8) return;
            if (Math.abs(dy) > Math.abs(dx)) {
                drag = null;
                return;
            }
            drag.active = true;
            drag.el.setPointerCapture(event.pointerId);
            drag.el.classList.add("dragging");
        }
        drag.dx = dx;
        drag.el.style.transform = `translateX(${dx}px) rotate(${dx / 24}deg)`;
        drag.el.dataset.intent = dx > SWIPE_THRESHOLD ? "yes" : dx < -SWIPE_THRESHOLD ? "no" : "";
    });

    const endDrag = (event) => {
        if (!drag || event.pointerId !== drag.id) return;
        const { el, dx, active } = drag;
        drag = null;
        if (!active) return;
        suppressClick = true;
        setTimeout(() => (suppressClick = false), 0);
        el.classList.remove("dragging");
        if (Math.abs(dx) > SWIPE_THRESHOLD && event.type === "pointerup") {
            vote(dx > 0 ? "yes" : "no");
        } else {
            el.style.transform = "";
            el.dataset.intent = "";
        }
    };
    card.addEventListener("pointerup", endDrag);
    card.addEventListener("pointercancel", endDrag);

    prefetch();
})();
