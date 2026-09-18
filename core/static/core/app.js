// Progressive enhancement only. With JavaScript off the page still works: every
// control submits with the Convert button, and the server enforces the same
// validation rules either way.

// Show the custom-rate input only when it is the selected rate source, so it
// never looks required when it is not.
(function () {
  const field = document.getElementById("custom-rate-field");
  const input = document.getElementById("id_custom_rate");
  const radios = document.querySelectorAll('input[name="source"]');
  if (!field || !input || !radios.length) return;

  function isCustom() {
    const checked = document.querySelector('input[name="source"]:checked');
    return checked !== null && checked.value === "custom";
  }

  function sync(focus) {
    const custom = isCustom();
    field.hidden = !custom;
    // A disabled input is not submitted, so switching away from Custom
    // cannot leave a stale rate behind for the server to apply.
    input.disabled = !custom;
    if (custom && focus) input.focus();
  }

  radios.forEach(function (radio) {
    radio.addEventListener("change", function () {
      sync(true);
    });
  });

  sync(false);
})();

// Flipping the direction converts straight away, so the other direction of the
// same amount does not need a second press of Convert.
(function () {
  const form = document.querySelector("form[method='post']");
  const directions = document.querySelectorAll('input[name="direction"]');
  const amount = document.getElementById("id_amount");
  if (!form || !directions.length || !amount) return;

  const SCROLL_FLAG = "hkd2usd.focusResult";
  let submitting = false;

  function convertNow() {
    if (submitting) return;
    // With no amount there is nothing to convert, and submitting would only
    // replace the form with a validation error the user did not ask for.
    if (!amount.value.trim()) return;
    submitting = true;
    try {
      sessionStorage.setItem(SCROLL_FLAG, "1");
    } catch (error) {
      /* private mode: the result simply stays where the reload puts it */
    }
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
  }

  directions.forEach(function (input) {
    input.addEventListener("click", function () {
      // Deferred so the radio's own checked state has settled before the form
      // is serialised; reading it any earlier can post the previous direction.
      window.setTimeout(convertNow, 0);
    });
  });
})();

// After an automatic conversion, bring the result into view. Without this the
// reload returns to the top of the page and the new figure can sit off-screen,
// which makes the conversion look as though nothing happened.
(function () {
  const SCROLL_FLAG = "hkd2usd.focusResult";
  const result = document.getElementById("result");
  if (!result) return;

  let pending = null;
  try {
    pending = sessionStorage.getItem(SCROLL_FLAG);
    sessionStorage.removeItem(SCROLL_FLAG);
  } catch (error) {
    return;
  }
  if (!pending) return;

  // On reload the browser restores its own scroll position, which undoes this
  // and leaves the page at the top. Take that over, but only for this reload —
  // the flag means an automatic conversion just happened.
  if ("scrollRestoration" in history) {
    history.scrollRestoration = "manual";
  }

  // Reveal after load as well: the restored position can be applied right up to
  // the load event, and an extra frame lets any layout settle first.
  function reveal() {
    window.requestAnimationFrame(function () {
      // "nearest" scrolls the minimum needed, and does nothing at all when the
      // result is already on screen. Aligning it to the top instead would push
      // the direction buttons off-screen and make flipping back awkward.
      result.scrollIntoView({ block: "nearest" });
    });
  }

  if (document.readyState === "complete") {
    reveal();
  } else {
    window.addEventListener("load", reveal, { once: true });
  }
})();
