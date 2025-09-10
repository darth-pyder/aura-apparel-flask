// static/js/account.js
document.addEventListener('DOMContentLoaded', () => {
    const editButton = document.getElementById('edit-button');
    const saveButton = document.getElementById('save-button');
    // Select all input fields that are not disabled
    const editableInputs = document.querySelectorAll('.account-form input:not([disabled])');

    if (editButton && saveButton && editableInputs) {
        editButton.addEventListener('click', () => {
            // Unlock all the input fields
            editableInputs.forEach(input => {
                input.readOnly = false;
            });

            // Change which button is visible
            editButton.style.display = 'none';
            saveButton.style.display = 'block';

            // Set focus to the first editable field for a great user experience
            editableInputs[0].focus();
        });
    }
});