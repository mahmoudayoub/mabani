
import { Amplify } from "aws-amplify";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import { Authenticator } from "@aws-amplify/ui-react";
import "@aws-amplify/ui-react/styles.css";

import Dashboard from "./pages/Dashboard";
import Profile from "./pages/Profile";
import KnowledgeBase from "./pages/KnowledgeBase";
import SafetyConfig from "./pages/SafetyConfig";
import SafetyLogs from "./pages/SafetyLogs";
import HealthAndSafety from "./pages/HealthAndSafety";
import FileProcessing from "./pages/FileProcessing";
import CodeAllocation from "./pages/CodeAllocation";
import PriceCodeChat from "./pages/PriceCodeChat";
import UnitRateChat from "./pages/UnitRateChat";
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
            signOut={signOut || (() => { })}
          >
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/profile" element={<Profile />} />
              <Route path="/health-safety" element={<HealthAndSafety />} />
              <Route path="/knowledge-base" element={<KnowledgeBase />} />
              <Route path="/safety-config" element={<SafetyConfig />} />
              <Route path="/safety-logs" element={<SafetyLogs />} />
              <Route path="/file-processing" element={<FileProcessing />} />
              <Route path="/code-allocation" element={<CodeAllocation />} />
              <Route path="/pricecode-chat" element={<PriceCodeChat />} />
              <Route path="/unitrate-chat" element={<UnitRateChat />} />
            </Routes>

          </Layout>
        </Router>
      )}
    </Authenticator>
  );
}

export default App;
