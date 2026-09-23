import React, { useState } from "react";
import {
  FiMail,
  FiLock,
  FiCheck,
  FiAlertCircle,
} from "react-icons/fi";
import API_URL from "../config";
import { apiFetch } from "../api";
import "./Auth.css";

function Signup({ onSignupSuccess, onSwitch }) {
  const [step, setStep] = useState(1); // 1: details, 2: otp

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [otp, setOtp] = useState("");

  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  const validateStep1 = () => {
    const newErrors = {};

    if (!email) {
      newErrors.email = "Email is required";
    } else if (!/\S+@\S+\.\S+/.test(email)) {
      newErrors.email = "Email is invalid";
    }

    if (!password) {
      newErrors.password = "Password is required";
    } else if (password.length < 6) {
      newErrors.password =
        "Password must be at least 6 characters";
    }

    if (!confirmPassword) {
      newErrors.confirmPassword =
        "Please confirm your password";
    } else if (password !== confirmPassword) {
      newErrors.confirmPassword =
        "Passwords do not match";
    }

    setErrors(newErrors);

    return Object.keys(newErrors).length === 0;
  };

  const handleSendOtp = async (e) => {
    e.preventDefault();

    if (!validateStep1()) return;

    setLoading(true);

    // Call backend to send OTP
    try {
      const response = await apiFetch(
        `${API_URL}/send-otp`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email,
          }),
        }
      );

      const data = response;

      if (data.success) {
        setStep(2);
        setErrors({});
      } else {
        setErrors({
          form:
            data.message ||
            "Error sending OTP",
        });
      }
    } catch (err) {
      console.error(
        "Error sending OTP:",
        err
      );

      setErrors({
        form: "Server error",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e) => {
    e.preventDefault();

    if (!otp) {
      setErrors({
        otp: "OTP is required",
      });

      return;
    }

    setLoading(true);

    try {
      const response = await apiFetch(
        `${API_URL}/verify-otp`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email,
            password,
            otp,
          }),
        }
      );

      const data = response;

      if (data.success) {
        onSignupSuccess();
      } else {
        setErrors({
          otp:
            data.message ||
            "Invalid OTP",
        });
      }
    } catch (err) {
      console.error(
        "OTP verification failed:",
        err
      );

      setErrors({
        form: "Verification failed",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-header">
        <h2 className="auth-title">
          {step === 1
            ? "Create Account"
            : "Verify Email"}
        </h2>

        <p className="auth-subtitle">
          {step === 1
            ? "Join MindWell today"
            : `Enter the code sent to ${email}`}
        </p>
      </div>

      {/* FORM ERROR */}
      {errors.form && (
        <div
          className="error-text"
          style={{
            justifyContent: "center",
            marginBottom: "10px",
          }}
        >
          <FiAlertCircle />{" "}
          {errors.form}
        </div>
      )}

      {/* STEP 1 - ACCOUNT DETAILS */}
      {step === 1 ? (
        <form
          onSubmit={handleSendOtp}
          className="auth-form"
        >
          {/* EMAIL */}
          <div className="form-group">
            <input
              type="email"
              placeholder="Email Address"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);

                if (errors.email) {
                  setErrors({
                    ...errors,
                    email: "",
                  });
                }
              }}
              className={`form-input ${
                errors.email ? "error" : ""
              }`}
              required
            />

            <FiMail className="input-icon" />

            {errors.email && (
              <span className="error-text">
                {errors.email}
              </span>
            )}
          </div>

          {/* PASSWORD */}
          <div className="form-group">
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => {
                setPassword(
                  e.target.value
                );

                if (errors.password) {
                  setErrors({
                    ...errors,
                    password: "",
                  });
                }
              }}
              className={`form-input ${
                errors.password ? "error" : ""
              }`}
              required
            />

            <FiLock className="input-icon" />

            {errors.password && (
              <span className="error-text">
                {errors.password}
              </span>
            )}
          </div>

          {/* CONFIRM PASSWORD */}
          <div className="form-group">
            <input
              type="password"
              placeholder="Confirm Password"
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(
                  e.target.value
                );

                if (
                  errors.confirmPassword
                ) {
                  setErrors({
                    ...errors,
                    confirmPassword: "",
                  });
                }
              }}
              className={`form-input ${
                errors.confirmPassword
                  ? "error"
                  : ""
              }`}
              required
            />

            <FiLock className="input-icon" />

            {errors.confirmPassword && (
              <span className="error-text">
                {errors.confirmPassword}
              </span>
            )}
          </div>

          {/* SEND OTP */}
          <button
            type="submit"
            className="auth-button"
            disabled={loading}
          >
            {loading
              ? "Sending OTP..."
              : "Send OTP"}
          </button>
        </form>
      ) : (
        /* STEP 2 - OTP */
        <form
          onSubmit={handleVerify}
          className="auth-form"
        >
          <div className="form-group">
            <input
              type="text"
              placeholder="Enter OTP"
              value={otp}
              onChange={(e) => {
                setOtp(e.target.value);

                if (errors.otp) {
                  setErrors({
                    ...errors,
                    otp: "",
                  });
                }
              }}
              className={`form-input ${
                errors.otp ? "error" : ""
              }`}
              required
            />

            <FiCheck className="input-icon" />

            {errors.otp && (
              <span className="error-text">
                {errors.otp}
              </span>
            )}
          </div>

          {/* VERIFY */}
          <button
            type="submit"
            className="auth-button"
            disabled={loading}
          >
            {loading
              ? "Verifying..."
              : "Verify & Create"}
          </button>

          {/* BACK */}
          <button
            type="button"
            onClick={() => {
              setStep(1);
              setOtp("");
              setErrors({});
            }}
            className="auth-link"
            style={{
              marginTop: "10px",
              fontSize: "0.9rem",
            }}
          >
            Back to details
          </button>
        </form>
      )}

      {/* LOGIN LINK */}
      {step === 1 && (
        <div className="auth-footer">
          Already have an account?{" "}

          <button
            onClick={onSwitch}
            className="auth-link"
          >
            Log In
          </button>
        </div>
      )}
    </div>
  );
}

export default Signup;