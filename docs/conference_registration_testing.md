# Conference registration testing

Run the idempotent setup command:

```bash
python manage.py setup_conference_registration
```

Sign in as an Event Administrator and open **Conference registration**. Confirm
that the `NESIF-2026` card provides both an **Open registration form** button and
a **Download registration QR** button. Scan the downloaded PNG from another
device; it must open the English public form.

## Example registration 1

- Full Name: Dr. Amina Mushi
- Institution Name: University of Dodoma
- Position / Title: Lecturer
- Email Address: amina@example.test
- Phone Number: +255 700 000 001
- Sessions: Basic Education Session; Science, Technology and Innovation Session

## Example registration 2

- Full Name: Eng. Baraka Mrema
- Institution Name: Arusha Technical College
- Position / Title: Director of Training
- Email Address: baraka@example.test
- Phone Number: +255 700 000 002
- Sessions: Higher Education and TVET Session; Fursa Women and Youth Innovation Clinic

After submission, confirm that a reference number is displayed. Approve the
registration in the staff workspace and verify that the participant portal and
participant QR/badge remain available through the existing registration system.
