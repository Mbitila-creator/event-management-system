document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("dynamic-event-form");

    if (!form) {
        return;
    }

    form.addEventListener("submit", (event) => {
        if (!form.checkValidity()) {
            event.preventDefault();
            form.reportValidity();
            return;
        }

        const submitButton = form.querySelector(".submit-button");

        if (submitButton) {
            submitButton.disabled = true;
            submitButton.textContent =
                document.documentElement.lang === "en"
                    ? "Submitting..."
                    : "Inawasilisha...";
        }
    });
});