document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("dynamic-event-form");

    if (!form) {
        return;
    }

    const submitButton = form.querySelector(".submit-button");
    const language =
        document.documentElement.lang === "en" ? "en" : "sw";

    const originalButtonText = submitButton
        ? submitButton.textContent.trim()
        : "";

    const clearErrors = () => {
        form.querySelectorAll(".field-error").forEach((element) => {
            element.textContent = "";
            element.classList.remove("is-visible");
        });

        form.querySelectorAll(".form-field").forEach((element) => {
            element.classList.remove("has-error");
        });

        const oldMessage = form.querySelector(
            ".submission-message"
        );

        if (oldMessage) {
            oldMessage.remove();
        }
    };

    const showGeneralMessage = (message, type = "error") => {
        const messageBox = document.createElement("div");
        messageBox.className =
            `submission-message submission-message-${type}`;
        messageBox.setAttribute("role", "alert");
        messageBox.textContent = message;

        form.prepend(messageBox);

        messageBox.scrollIntoView({
            behavior: "smooth",
            block: "center",
        });
    };

    const showFieldErrors = (errors) => {
        let firstInvalidField = null;

        Object.entries(errors).forEach(
            ([questionId, message]) => {
                const fieldWrapper = form.querySelector(
                    `[data-question-id="${questionId}"]`
                );

                const errorElement = document.getElementById(
                    `error-question-${questionId}`
                );

                if (fieldWrapper) {
                    fieldWrapper.classList.add("has-error");

                    if (!firstInvalidField) {
                        firstInvalidField = fieldWrapper;
                    }
                }

                if (errorElement) {
                    errorElement.textContent = message;
                    errorElement.classList.add("is-visible");
                }
            }
        );

        if (firstInvalidField) {
            firstInvalidField.scrollIntoView({
                behavior: "smooth",
                block: "center",
            });
        }
    };

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearErrors();

        if (!form.checkValidity()) {
            form.reportValidity();
            return;
        }

        if (submitButton) {
            submitButton.disabled = true;
            submitButton.textContent =
                language === "en"
                    ? "Submitting..."
                    : "Inawasilisha...";
        }

        try {
            const formData = new FormData(form);

            const response = await fetch(
                window.location.href,
                {
                    method: "POST",
                    body: formData,
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                    },
                }
            );

            const data = await response.json();

            if (!response.ok || !data.success) {
                showGeneralMessage(
                    data.message ||
                        (
                            language === "en"
                                ? "Please correct the form errors."
                                : "Tafadhali rekebisha makosa ya fomu."
                        )
                );

                if (data.errors) {
                    showFieldErrors(data.errors);
                }

                return;
            }

            showGeneralMessage(
                data.message ||
                    (
                        language === "en"
                            ? "Submission completed successfully."
                            : "Fomu imewasilishwa kwa mafanikio."
                    ),
                "success"
            );

            window.location.assign(data.redirect_url);
        } catch (error) {
            console.error(error);

            showGeneralMessage(
                language === "en"
                    ? "The form could not be submitted. Please try again."
                    : "Fomu haikuweza kuwasilishwa. Tafadhali jaribu tena."
            );
        } finally {
            if (submitButton) {
                submitButton.disabled = false;
                submitButton.textContent = originalButtonText;
            }
        }
    });
});