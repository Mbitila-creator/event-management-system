document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".messagelist li").forEach(function (message) {
        const closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.className = "ems-message-close";
        closeButton.setAttribute("aria-label", "Dismiss notification");
        closeButton.textContent = "×";
        message.appendChild(closeButton);

        let timeout;
        const dismiss = function () {
            window.clearTimeout(timeout);
            message.classList.add("ems-message-hiding");
            window.setTimeout(function () { message.remove(); }, 260);
        };
        const scheduleDismissal = function () {
            timeout = window.setTimeout(dismiss, 7000);
        };
        closeButton.addEventListener("click", dismiss);
        message.addEventListener("mouseenter", function () {
            window.clearTimeout(timeout);
        });
        message.addEventListener("mouseleave", scheduleDismissal);
        scheduleDismissal();
    });
});
