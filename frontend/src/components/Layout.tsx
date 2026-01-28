import React, { useState, useEffect } from "react";
import { Link, useLocation } from "react-router-dom";

interface LayoutProps {
  children: React.ReactNode;
  user: {
    signInDetails?: {
      loginId?: string;
    };
  };
  signOut: () => void;
}

const Layout: React.FC<LayoutProps> = ({ children, user, signOut }) => {
  const location = useLocation();
  const [firstName, setFirstName] = useState<string | null>(null);

  // Track page changes for internal analytics
  React.useEffect(() => {
    console.log(`Page view: ${location.pathname}${location.search}`);
  }, [location]);

  // Fetch user's first name
  useEffect(() => {
    const loadFirstName = async () => {
      try {
        const authModule = await import("aws-amplify/auth");
        const attributes = await authModule.fetchUserAttributes();
        const givenName = attributes.given_name;
        if (givenName) {
          setFirstName(givenName);
        }
      } catch (error) {
        // Silently fail - will just show email as fallback
      }
    };

    if (user) {
      loadFirstName();
    }
  }, [user]);

  const navigation = [
    { name: "Dashboard", href: "/", current: location.pathname === "/" },
    {
      name: "Health & Safety",
      href: "/health-safety",
      current: location.pathname.startsWith("/health-safety") ||
        location.pathname.startsWith("/knowledge-base") ||
        location.pathname.startsWith("/safety-config") ||
        location.pathname.startsWith("/safety-logs"),
    },
    {
      name: "Unit Rate Allocation",
      href: "/file-processing",
      current: location.pathname === "/file-processing",
    },
    {
      name: "Price Code Allocation",
      href: "/code-allocation",
      current: location.pathname === "/code-allocation",
    },
    {
      name: "Price Code Chat",
      href: "/pricecode-chat",
      current: location.pathname === "/pricecode-chat",
    },
    {
      name: "Unit Rate Chat",
      href: "/unitrate-chat",
      current: location.pathname === "/unitrate-chat",
    },
    {
      name: "Profile",
      href: "/profile",
      current: location.pathname === "/profile",
    },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navigation */}
      <nav className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex">
              <div className="flex-shrink-0 flex items-center">
                <h1 className="text-xl font-bold text-black">TaskFlow</h1>
              </div>
              <div className="hidden sm:ml-6 sm:flex sm:space-x-8">
                {navigation.map((item) => (
                  <Link
                    key={item.name}
                    to={item.href}
                    className={`${item.current
                      ? "border-primary-500 text-black"
                      : "border-transparent text-gray-600 hover:text-black hover:border-gray-300"
                      } inline-flex items-center px-1 pt-1 border-b-2 text-sm font-medium`}
                  >
                    {item.name}
                  </Link>
                ))}
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-sm text-gray-700">
                Welcome, {firstName || user?.signInDetails?.loginId || "User"}
              </span>
              <button
                onClick={signOut}
                className="bg-primary-500 hover:bg-primary-600 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
              >
                Sign Out
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Main content */}
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">{children}</main>
    </div>
  );
};

export default Layout;
