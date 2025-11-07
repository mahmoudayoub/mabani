import React from "react";
import { Amplify } from "aws-amplify";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import { Authenticator } from "@aws-amplify/ui-react";
import "@aws-amplify/ui-react/styles.css";

import Dashboard from "./pages/Dashboard";
import Profile from "./pages/Profile";
import Layout from "./components/Layout";

// Configure Amplify
const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID;
const userPoolClientId = import.meta.env.VITE_COGNITO_USER_POOL_CLIENT_ID;
const region = import.meta.env.VITE_COGNITO_REGION || "eu-west-1";

const amplifyConfig: Record<string, unknown> = {};

if (userPoolId && userPoolClientId) {
  amplifyConfig.Auth = {
    Cognito: {
      userPoolId,
      userPoolClientId,
      loginWith: {
        email: true,
      },
    },
  };
} else {
  console.warn(
    "Auth UserPool not configured. Missing VITE_COGNITO_USER_POOL_ID or VITE_COGNITO_USER_POOL_CLIENT_ID"
  );
}

if (import.meta.env.VITE_API_BASE_URL) {
  amplifyConfig.API = {
    REST: {
      api: {
        endpoint: import.meta.env.VITE_API_BASE_URL,
        region,
      },
    },
  };
}

Amplify.configure(amplifyConfig);

function App() {
  return (
    <Authenticator
      hideSignUp={false}
      loginMechanisms={["email"]}
      formFields={{
        signIn: {
          username: {
            label: "Email",
            placeholder: "Enter your email",
            isRequired: true,
            type: "email",
          },
        },
      }}
      signUpAttributes={["email", "given_name", "family_name"]}
      components={{
        SignIn: {
          Header() {
            return (
              <div className="text-center mb-6">
                <h1 className="text-3xl font-bold text-gray-900 mb-2">
                  Welcome to TaskFlow
                </h1>
                <p className="text-gray-600 text-sm">
                  Sign in to your account to continue
                </p>
              </div>
            );
          },
        },
        SignUp: {
          Header() {
            return (
              <div className="text-center mb-6">
                <h1 className="text-3xl font-bold text-gray-900 mb-2">
                  Create your account
                </h1>
                <p className="text-gray-600 text-sm">
                  Join TaskFlow and start managing your tasks
                </p>
              </div>
            );
          },
        },
      }}
    >
      {({ signOut, user }) => (
        <Router>
          <Layout
            user={user || { signInDetails: { loginId: undefined } }}
            signOut={signOut || (() => {})}
          >
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/profile" element={<Profile />} />
            </Routes>
          </Layout>
        </Router>
      )}
    </Authenticator>
  );
}

export default App;
