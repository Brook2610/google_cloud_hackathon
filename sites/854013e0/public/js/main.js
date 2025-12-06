// public/js/main.js

document.addEventListener('DOMContentLoaded', () => {
    const contactForm = document.getElementById('contactForm');

    if (contactForm) {
        contactForm.addEventListener('submit', function(e) {
            e.preventDefault();

            // Simple form validation
            const name = document.getElementById('name').value;
            const email = document.getElementById('email').value;
            const message = document.getElementById('message').value;

            if (name === "" || email === "" || message === "") {
                alert("Please fill out all fields.");
                return;
            }

            // In a real application, you would send this data to a server here.
            console.log('Form Submitted:', { name, email, message });

            // Provide user feedback
            alert("Thank you for your message! We will get back to you shortly.");

            // Reset the form
            contactForm.reset();
        });
    }
});