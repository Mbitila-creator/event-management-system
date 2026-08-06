document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-password-target]").forEach(function (button) {
        const input = document.getElementById(button.dataset.passwordTarget);
        if (!input) return;
        button.addEventListener("click", function () {
            const showing = input.type === "text";
            input.type = showing ? "password" : "text";
            button.setAttribute("aria-pressed", String(!showing));
            button.setAttribute(
                "aria-label",
                showing ? button.dataset.showLabel : button.dataset.hideLabel
            );
            input.focus();
        });
    });
});
