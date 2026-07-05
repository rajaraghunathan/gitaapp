
let otpVerified = null;
// Common Unified Handler to Process JSON Authorization Submissions
function executeAuth(event, endpoint, formElement) {
    event.preventDefault();

    if (formElement.id === "studentRegisterForm") {
        if (!otpVerified){
            showToast("Get OTP Verified First");
            return;
        } else {
            document.querySelector ('#studentRegisterForm input[name="email"]').disabled = false;
        }
    }
    const formData = new FormData(formElement);
    const payload = {};
    formData.forEach((value, key) => payload[key] = value);
    fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(res => res.json().then(data => ({ status: res.status, body: data })))
    .then(resObj => {
        if(resObj.body.success === true) {
            window.location.href = resObj.body.redirect;
        } else {
            showToast("Authentication Error: " + (resObj.body.message || "Operation Rejected"),"danger")
        }
    })
    .catch(err => alert("Network transmission breakdown: " + err));
}

// Wait for the DOM to be fully ready
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.modal').forEach(modalElement => {
        modalElement.addEventListener('show.bs.modal', function () {
            // Clear all text inputs
            const inputs = this.querySelectorAll('input, textarea, select');
            inputs.forEach(input => {
                input.value = '';
                input.checked = false;
                input.disabled = false;
            });

            if (this.id === "studentRegisterModal") {
                otpVerified = null;
                document.getElementById('otp-button').textContent = 'Get OTP';
                document.querySelector ('#studentRegisterForm input[name="email"]').disabled = false;
            }

            if (this.id === "studentLoginModal") {
                document.getElementById("resetPassForm").style.display = "none";
                document.getElementById("alert-msg").textContent = "";
            }

            const forms = this.querySelectorAll('form');
            forms.forEach(form => form.classList.remove('was-validated'));
        });
    });

    const secureFields = document.querySelectorAll('#otp, #student-password');
    secureFields.forEach(field => {
        field.addEventListener('paste', function(e) {
            e.preventDefault();

            // Extract raw string characters
            let rawText = (e.clipboardData || window.clipboardData).getData('text');

            if (this.id === 'otp') {
                // Keep ONLY numbers and limit to 6 digits for OTP
                this.value = rawText.replace(/\D/g, '').slice(0, 6);
            } else {
                // Remove hidden email client tags/spaces but keep letters and symbols
                this.value = rawText.replace(/<\/?[^>]+(>|$)/g, "").trim();
            }

            this.dispatchEvent(new Event('input'));
        });
    });

    document.getElementById("newPassword").addEventListener("input", checkPasswordMatch);
    document.getElementById("confirmPassword").addEventListener("input", checkPasswordMatch);

});

function getOtp(el) {
    if (el.textContent === "Get OTP") {
        document.getElementById("otp").value = "";
        const emailInput = document.querySelector('#studentRegisterModal input[name="email"]');
        const emailValue = emailInput.value;
        if (emailValue === '') {showToast("Enter email first", "warning"); return;}
        fetch('/api/get_otp', {method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(emailValue)
        }).then(res => res.json()).then(data => {
            if(data.success === true) {
                document.getElementById('otp-button').textContent = "Submit OTP";
                const timerEl = document.getElementById("timer")
                // startTimer(300, timerEl, display); // Timer Set in seconds
                document.querySelector ('#studentRegisterForm input[name="email"]').disabled = true;
                showToast(data.message, "success");
            } else {
                showToast(data.message, "danger")
            }
        })
    } else if (el.textContent === "Submit OTP") {
        const otp = document.getElementById("otp").value
        if (otp === "") { showToast("Enter OTP","warning"); return;}
        fetch('/api/sumbit_otp', {method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(otp)
        }).then(res => res.json()).then(data => {
            if(data.success === true) {
                otpVerified = "Verified";
                el.textContent = "Verified";
                showToast(data.message, "success");
            } else {
                if (data.session === false) {
                  document.getElementById('otp-button').textContent = "Get OTP";
                }
                showToast(data.message, "danger")
            }
        })
    }
}

// 1. Create a global variable to hold the timer reference ID
let otpIntervalId = null;
function startTimer(duration, timerEl, display) {
    let timer = duration, minutes, seconds;

    // 2. SAFETY CHECK: If a timer is already running, kill it before starting a new one
    if (otpIntervalId !== null) {
        clearInterval(otpIntervalId);
    }

    otpIntervalId = setInterval(function () {
        minutes = parseInt(timer / 60, 10);
        seconds = parseInt(timer % 60, 10);

        minutes = minutes < 10 ? "0" + minutes : minutes;
        seconds = seconds < 10 ? "0" + seconds : seconds;
        timerEl.textContent = minutes + ":" + seconds;
        display.textContent = "Submit OTP";

        // 3. Check if the time has run out
        if (--timer < 0) {
            // Stop the loop completely
            clearInterval(otpIntervalId);
            otpIntervalId = null; // Clear the reference holder

            // Add your expired actions here
            display.textContent = "Get OTP";
            timerEl.textContent = "00:00";
            otpVerified = null;
            showToast("OTP Expired");
        }
    }, 1000);
}

function userForgotPassword () {
    document.getElementById("alert-msg").textContent = "";
    const emailInput = document.querySelector('#studentLoginModal input[name="email"]');
    const emailValue = emailInput.value;
    if (emailValue === "" ) {
        document.getElementById("alert-msg").textContent = "Enter Email First";
        showToast("Enter Email First", "warning");
        return;
    }
    fetch('/api/auth/forgotpassword', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(emailValue)
    }).then(res => res.json()).then(data => {
        if(data.success === true) {
            document.getElementById("resetPassForm").style.display = "block";
            document.getElementById("alert-msg").textContent = "";
            document.querySelector ('#studentLoginForm input[name="email"]').disabled = true;
            showToast(data.message, "success")
        } else {
            if (data.session === true) {
                document.getElementById("resetPassForm").style.display = "block";
                document.querySelector ('#studentLoginForm input[name="email"]').disabled = true;
            }
            document.getElementById("alert-msg").textContent = data.message;
            showToast(data.message, "warning")
        }
    })
}

function checkPasswordMatch() {
    const newPassword = document.getElementById("newPassword");
    const confirmPassword = document.getElementById("confirmPassword");
    if (newPassword.value !== confirmPassword.value) {
        confirmPassword.setCustomValidity("Passwords do not match.");
    } else {
        confirmPassword.setCustomValidity(""); // Reset validity if they match
    }
}

function studentPasswordReset(event,formElement) {
    event.preventDefault();
    const emailInput = document.querySelector('#studentLoginModal input[name="email"]');
    const emailValue = emailInput.value;
    if (emailValue === "" ) {
        document.getElementById("alert-msg").textContent = "Enter Email First";
        showToast("Enter Email First", "warning");
        return;
    }
    checkPasswordMatch();
    if (!formElement.checkValidity()) {
        formElement.classList.add('was-validated');
        return;
    }
    const newPassword = document.getElementById("newPassword").value;
    const otp = document.getElementById("reset-otp").value;
    const payload = {
        "email": emailValue,
        "newPassword": newPassword,
        "otp": otp
    };
    fetch('/api/auth/changepassword', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(res => res.json()).then(data => {
        if(data.success) {
            showToast(data.message, "success");
            document.getElementById("alert-msg").textContent = "";
            document.getElementById("resetPassForm").style.display = "none";
            document.querySelector ('#studentLoginForm input[name="email"]').disabled = false;
            document.querySelectorAll("#resetPassForm input").forEach(input=>{input.value = ""})
        } else {
            if (data.session === false) {
                document.getElementById("resetPassForm").style.display = "none";
                document.querySelectorAll("#resetPassForm input").forEach(input=>{input.value = ""})
            }
            document.getElementById("alert-msg").textContent = data.message
            showToast(data.message, "warning");
        }
    })
    .catch(err => alert("Network transmission breakdown: " + err));
}

