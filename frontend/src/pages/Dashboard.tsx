import React from "react";
import { useNavigate } from "react-router-dom";

const Dashboard: React.FC = () => {
  const navigate = useNavigate();


  const modules = [
    {
      id: "hs",
      name: "Health & Safety",
      acronym: "H&S",
      description: "AI-powered H&S observations logging",
      color: "primary",
      path: "/health-safety",
      icon: (
        <svg
          className="w-8 h-8"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
          />
        </svg>
      ),
    },
    {
      id: "qc",
      name: "Quality Control",
      acronym: "QC",
      description: "AI-powered observations logging",
      color: "primary",
      path: undefined,
      icon: (
        <svg
          className="w-8 h-8"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      ),
    },
    {
      id: "ai-t",
      name: "Price Code Allocation",
      acronym: "AI-C",
      description: "AI-driven price code matching",
      color: "primary",
      path: "/code-allocation",
      icon: (
        <svg
          className="w-8 h-8"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
          />
        </svg>
      ),
    },
    {
      id: "ai-p",
      name: "Unit Rate Allocation",
      acronym: "AI-P",
      description: "AI-driven unit rate matching with Chatbot",
      color: "primary",
      path: "/file-processing",
      icon: (
        <svg
          className="w-8 h-8"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      ),
    },
  ];

  return (
    <div className="px-4 py-6 sm:px-6 lg:px-8">
      {/* Welcome Section */}
      <div className="mb-6 sm:mb-8">
        <h1 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-gray-900 mb-2">
          Welcome back!
        </h1>
        <p className="text-sm sm:text-base text-gray-600">
          Here's what's happening with your projects today.
        </p>
      </div>

      {/* Main Content Grid */}
      <div className="mb-6 sm:mb-8">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 sm:p-6">
          <h2 className="text-lg sm:text-xl font-semibold text-gray-900 mb-4 sm:mb-6">
            Quick Actions
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 sm:gap-6">
            {modules.map((module) => (
              <button
                key={module.id}
                onClick={() => module.path && navigate(module.path)}
                className="bg-primary-50 border-2 border-primary-200 rounded-lg p-4 sm:p-6 text-left hover:bg-primary-100 hover:border-primary-300 transition-all group"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="p-2 bg-primary-500 rounded-lg text-white group-hover:bg-primary-600 transition-colors">
                    {module.icon}
                  </div>
                  <span className="text-xs sm:text-sm font-bold text-primary-700 bg-primary-100 px-2 py-1 rounded">
                    {module.acronym}
                  </span>
                </div>
                <h3 className="font-semibold text-gray-900 mb-2 text-sm sm:text-base">
                  {module.name}
                </h3>
                <p className="text-xs sm:text-sm text-gray-600">
                  {module.description}
                </p>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Performance Overview */}

    </div >
  );
};

export default Dashboard;
