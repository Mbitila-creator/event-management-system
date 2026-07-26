document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("dynamic-event-form");

    if (!form) {
        return;
    }

    const submitButton = form.querySelector(".submit-button");
    const steps = Array.from(form.querySelectorAll(".wizard-step"));
    const previousButton = form.querySelector(".wizard-previous");
    const nextButton = form.querySelector(".wizard-next");
    const progressTrack = form.querySelector(".wizard-progress-track");
    const progressFill = form.querySelector(".wizard-progress-fill");
    const progressPercent = form.querySelector(".wizard-progress-percent");
    const stepCount = form.querySelector(".wizard-step-count");
    const stepDots = form.querySelector(".wizard-step-dots");
    const reviewContainer = form.querySelector(".review-sections");
    const questionFields = Array.from(
        form.querySelectorAll(".form-field")
    );
    const language =
        document.documentElement.lang === "en" ? "en" : "sw";
    let currentStep = 0;

    questionFields.forEach((field, index) => {
        const numberElement = field.querySelector(".question-number");

        if (numberElement) {
            numberElement.textContent = `${index + 1}.`;
        }
    });

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

    const text = {
        step: language === "en" ? "Step" : "Hatua",
        of: language === "en" ? "of" : "kati ya",
        complete: language === "en" ? "complete" : "imekamilika",
        notAnswered:
            language === "en" ? "Not answered" : "Haijajibiwa",
        noFile:
            language === "en" ? "No file selected" : "Hakuna faili",
        edit: language === "en" ? "Edit" : "Hariri",
    };

    const getFieldValue = (field) => {
        const controls = Array.from(
            field.querySelectorAll("input, select, textarea")
        );
        const checked = controls.filter(
            (control) =>
                (control.type === "checkbox" ||
                    control.type === "radio") &&
                control.checked
        );

        if (checked.length) {
            return checked.map((control) => {
                const choice = control.closest(".choice-item");
                return choice
                    ? choice.textContent.trim()
                    : control.value;
            }).join(", ");
        }

        const control = controls.find(
            (item) =>
                item.type !== "checkbox" &&
                item.type !== "radio" &&
                item.type !== "hidden"
        );

        if (!control) {
            return text.notAnswered;
        }

        if (control.type === "file") {
            return control.files && control.files.length
                ? Array.from(control.files)
                    .map((file) => file.name)
                    .join(", ")
                : text.noFile;
        }

        if (control.tagName === "SELECT" && control.selectedIndex >= 0) {
            return control.value
                ? control.options[control.selectedIndex].text.trim()
                : text.notAnswered;
        }

        return control.value.trim() || text.notAnswered;
    };

    const buildReview = () => {
        if (!reviewContainer) {
            return;
        }

        reviewContainer.replaceChildren();

        steps.slice(0, -1).forEach((step, index) => {
            const section = document.createElement("section");
            section.className = "review-section";

            const heading = document.createElement("div");
            heading.className = "review-section-heading";

            const title = document.createElement("h4");
            title.textContent = step.dataset.stepTitle;

            const editButton = document.createElement("button");
            editButton.type = "button";
            editButton.className = "review-edit-button";
            editButton.textContent = text.edit;
            editButton.addEventListener("click", () => showStep(index));

            heading.append(title, editButton);
            section.append(heading);

            step.querySelectorAll(".form-field").forEach((field) => {
                const item = document.createElement("div");
                item.className = "review-item";

                const label = document.createElement("dt");
                label.textContent = field.dataset.questionLabel;

                const value = document.createElement("dd");
                value.textContent = getFieldValue(field);

                item.append(label, value);
                section.append(item);
            });

            reviewContainer.append(section);
        });
    };

    const updateProgress = () => {
        const total = steps.length;
        const percent = total
            ? Math.round(((currentStep + 1) / total) * 100)
            : 0;

        if (stepCount) {
            stepCount.textContent =
                `${text.step} ${currentStep + 1} ${text.of} ${total}`;
        }

        if (progressPercent) {
            progressPercent.textContent = `${percent}% ${text.complete}`;
        }

        if (progressFill) {
            progressFill.style.width = `${percent}%`;
        }

        if (progressTrack) {
            progressTrack.setAttribute("aria-valuenow", String(percent));
        }

        form.querySelectorAll(".wizard-step-dot").forEach((dot, index) => {
            dot.classList.toggle("is-active", index === currentStep);
            dot.classList.toggle("is-complete", index < currentStep);
            dot.setAttribute(
                "aria-current",
                index === currentStep ? "step" : "false"
            );
        });
    };

    const showStep = (index, focusHeading = true) => {
        currentStep = Math.max(0, Math.min(index, steps.length - 1));

        steps.forEach((step, stepIndex) => {
            const active = stepIndex === currentStep;
            step.hidden = !active;
            step.classList.toggle("is-active", active);

            const eyebrow = step.querySelector(".section-eyebrow");
            if (eyebrow) {
                eyebrow.textContent =
                    `${text.step} ${stepIndex + 1} ${text.of} ${steps.length}`;
            }
        });

        if (currentStep === steps.length - 1) {
            buildReview();
        }

        if (previousButton) {
            previousButton.hidden = currentStep === 0;
        }

        if (nextButton) {
            nextButton.hidden = currentStep === steps.length - 1;
        }

        if (submitButton) {
            submitButton.hidden = currentStep !== steps.length - 1;
        }

        updateProgress();

        if (focusHeading) {
            const heading = steps[currentStep].querySelector("h3");
            heading?.setAttribute("tabindex", "-1");
            heading?.focus({preventScroll: true});
            form.querySelector(".wizard-progress")?.scrollIntoView({
                behavior: "smooth",
                block: "start",
            });
        }
    };

    const validateCurrentStep = () => {
        const step = steps[currentStep];
        const controls = Array.from(
            step.querySelectorAll("input, select, textarea")
        );
        const invalid = controls.find((control) => !control.checkValidity());

        if (!invalid) {
            return true;
        }

        invalid.reportValidity();
        invalid.focus({preventScroll: true});
        invalid.closest(".form-field")?.scrollIntoView({
            behavior: "smooth",
            block: "center",
        });
        return false;
    };

    if (steps.length) {
        form.classList.add("wizard-ready");

        steps.forEach((step, index) => {
            if (!stepDots) {
                return;
            }

            const item = document.createElement("li");
            const button = document.createElement("button");
            button.type = "button";
            button.className = "wizard-step-dot";
            button.setAttribute(
                "aria-label",
                `${text.step} ${index + 1}: ${step.dataset.stepTitle}`
            );
            button.addEventListener("click", () => {
                if (index < currentStep) {
                    showStep(index);
                }
            });
            item.append(button);
            stepDots.append(item);
        });

        previousButton?.addEventListener(
            "click",
            () => showStep(currentStep - 1)
        );

        nextButton?.addEventListener("click", () => {
            if (validateCurrentStep()) {
                showStep(currentStep + 1);
            }
        });

        showStep(0, false);
    }

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
            const firstInvalid = form.querySelector(":invalid");
            const invalidStep = steps.findIndex(
                (step) => firstInvalid && step.contains(firstInvalid)
            );

            if (invalidStep >= 0) {
                showStep(invalidStep);
            }

            firstInvalid?.reportValidity();
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

                    const firstErrorId = Object.keys(data.errors)[0];
                    const errorField = form.querySelector(
                        `[data-question-id="${firstErrorId}"]`
                    );
                    const errorStep = steps.findIndex(
                        (step) => errorField && step.contains(errorField)
                    );

                    if (errorStep >= 0) {
                        showStep(errorStep);
                    }
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
