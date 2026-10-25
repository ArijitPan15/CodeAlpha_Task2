// Confirmation is attached only to explicit POST forms; the backend still
// enforces ownership, event dates and CSRF protection.
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const prompt = form.dataset.confirm;
      if (prompt && !window.confirm(prompt)) {
        event.preventDefault();
      }
    });
  });
});
