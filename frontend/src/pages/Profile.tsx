import React, { useState, useEffect } from "react";
import { useAuthenticator } from "@aws-amplify/ui-react";

interface UserAttributes {
  email?: string;
  given_name?: string;
  family_name?: string;
  position?: string;
  sub?: string;
  email_verified?: string;
}

const Profile: React.FC = () => {
  const { user } = useAuthenticator();
  const [userAttributes, setUserAttributes] = useState<UserAttributes>({});
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editForm, setEditForm] = useState({
    given_name: "",
    family_name: "",
    position: "",
  });

  useEffect(() => {
    const loadUserAttributes = async () => {
      try {
        // Import and use fetchUserAttributes from aws-amplify/auth
        const authModule = await import("aws-amplify/auth");
        const attributes = await authModule.fetchUserAttributes();
        const allAttributes = await attributes;
        // Handle custom attributes that might come with or without "custom:" prefix
        const position =
          allAttributes["custom:position"] || allAttributes.position || "";
        setUserAttributes({
          ...allAttributes,
          position,
        });
        setEditForm({
          given_name: allAttributes.given_name || "",
          family_name: allAttributes.family_name || "",
          position,
        });
      } catch (error) {
        // Fallback: extract from user object if available
        console.error("Error fetching user attributes:", error);
        const email = user?.signInDetails?.loginId || undefined;
        setUserAttributes({
          email,
        });
        setEditForm({
          given_name: "",
          family_name: "",
          position: "",
        });
      } finally {
        setLoading(false);
      }
    };

    if (user) {
      loadUserAttributes();
    } else {
      setLoading(false);
    }
  }, [user]);

  const handleEdit = () => {
    setIsEditing(true);
    setEditForm({
      given_name: userAttributes.given_name || "",
      family_name: userAttributes.family_name || "",
      position: userAttributes.position || "",
    });
  };

  const handleCancel = () => {
    setIsEditing(false);
    setEditForm({
      given_name: userAttributes.given_name || "",
      family_name: userAttributes.family_name || "",
      position: userAttributes.position || "",
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const authModule = await import("aws-amplify/auth");
      const updates: Record<string, string> = {};

      if (editForm.given_name !== (userAttributes.given_name || "")) {
        updates.given_name = editForm.given_name;
      }
      if (editForm.family_name !== (userAttributes.family_name || "")) {
        updates.family_name = editForm.family_name;
      }
      if (editForm.position !== (userAttributes.position || "")) {
        updates["custom:position"] = editForm.position;
      }

      if (Object.keys(updates).length > 0) {
        await authModule.updateUserAttributes({
          userAttributes: updates,
        });

        // Update state immediately with saved values for instant UI feedback
        const updatedAttributes = {
          ...userAttributes,
          given_name:
            updates.given_name !== undefined
              ? updates.given_name
              : userAttributes.given_name,
          family_name:
            updates.family_name !== undefined
              ? updates.family_name
              : userAttributes.family_name,
          position:
            updates["custom:position"] !== undefined
              ? updates["custom:position"]
              : userAttributes.position,
        };
        setUserAttributes(updatedAttributes);

        // Also update the edit form to reflect the saved values
        setEditForm({
          given_name: updatedAttributes.given_name || "",
          family_name: updatedAttributes.family_name || "",
          position: updatedAttributes.position || "",
        });

        // Optionally reload from server to ensure consistency (in background)
        try {
          const attributes = await authModule.fetchUserAttributes();
          const position =
            attributes["custom:position"] || attributes.position || "";
          setUserAttributes({
            ...attributes,
            position,
          });
        } catch (error) {
          // Silently fail - we already updated state optimistically
          console.warn("Could not refresh attributes:", error);
        }
      }

      setIsEditing(false);
    } catch (error) {
      console.error("Error updating user attributes:", error);
      alert("Failed to update profile. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const fullName =
    userAttributes.given_name || userAttributes.family_name
      ? `${userAttributes.given_name || ""} ${
          userAttributes.family_name || ""
        }`.trim()
      : null;

  const email = userAttributes.email || user?.signInDetails?.loginId || "N/A";
  const userId = userAttributes.sub || user?.userId || "N/A";

  const profileFields = [
    {
      label: "Email",
      value: email,
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
          />
        </svg>
      ),
    },
    {
      label: "User ID",
      value: userId,
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M10 6H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V8a2 2 0 00-2-2h-5m-4 0V5a2 2 0 114 0v1m-4 0a2 2 0 104 0m-5 8a2 2 0 100-4 2 2 0 000 4zm0 0c1.306 0 2.417.835 2.83 2M9 14a3.001 3.001 0 00-2.83 2M15 11h3m-3 4h2"
          />
        </svg>
      ),
    },
    {
      label: "Email Verified",
      value: userAttributes.email_verified === "true" ? "Yes" : "No",
      icon: (
        <svg
          className="w-5 h-5"
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
  ];

  if (loading) {
    return (
      <div className="px-4 py-6 sm:px-0">
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="px-4 py-6 sm:px-0">
      <div className="space-y-6">
        {/* Profile Header */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
          <div className="flex flex-col items-center text-center space-y-4">
            <div className="flex-1 min-w-0 w-full">
              <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 mb-2">
                {fullName || "User Profile"}
              </h1>
              <p className="text-sm sm:text-base text-gray-600">{email}</p>
              {userAttributes.email_verified === "true" && (
                <div className="mt-2 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                  <svg
                    className="w-3 h-3 mr-1"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                      clipRule="evenodd"
                    />
                  </svg>
                  Verified
                </div>
              )}
            </div>
            <div className="flex-shrink-0">
              <div className="w-20 h-20 sm:w-24 sm:h-24 bg-primary-500 rounded-full flex items-center justify-center">
                <span className="text-2xl sm:text-3xl font-bold text-white">
                  {fullName
                    ? fullName
                        .split(" ")
                        .map((n) => n[0])
                        .join("")
                        .toUpperCase()
                        .slice(0, 2)
                    : email[0].toUpperCase()}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Personal Information */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg sm:text-xl font-semibold text-gray-900">
              Personal Information
            </h2>
            {!isEditing && (
              <button
                onClick={handleEdit}
                className="flex items-center space-x-2 px-4 py-2 text-sm font-medium text-primary-600 bg-primary-50 rounded-lg hover:bg-primary-100 transition-colors"
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                  />
                </svg>
                <span>Edit</span>
              </button>
            )}
          </div>

          {isEditing ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-500 uppercase tracking-wide mb-2">
                    First Name
                  </label>
                  <input
                    type="text"
                    value={editForm.given_name}
                    onChange={(e) =>
                      setEditForm({ ...editForm, given_name: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm sm:text-base text-gray-900"
                    placeholder="Enter first name"
                  />
                </div>
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-500 uppercase tracking-wide mb-2">
                    Last Name
                  </label>
                  <input
                    type="text"
                    value={editForm.family_name}
                    onChange={(e) =>
                      setEditForm({ ...editForm, family_name: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm sm:text-base text-gray-900"
                    placeholder="Enter last name"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs sm:text-sm font-medium text-gray-500 uppercase tracking-wide mb-2">
                  Position
                </label>
                <input
                  type="text"
                  value={editForm.position}
                  onChange={(e) =>
                    setEditForm({ ...editForm, position: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm sm:text-base text-gray-900"
                  placeholder="Enter position"
                />
              </div>
              <div className="flex items-center justify-end space-x-3 pt-4">
                <button
                  onClick={handleCancel}
                  disabled={saving}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="px-4 py-2 text-sm font-medium text-white bg-primary-500 rounded-lg hover:bg-primary-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
                >
                  {saving ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      <span>Saving...</span>
                    </>
                  ) : (
                    <span>Save</span>
                  )}
                </button>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <p className="text-xs sm:text-sm font-medium text-gray-500 uppercase tracking-wide mb-1">
                  First Name
                </p>
                <p className="text-sm sm:text-base text-gray-900">
                  {userAttributes.given_name || (
                    <span className="text-gray-400 italic">Not set</span>
                  )}
                </p>
              </div>
              <div>
                <p className="text-xs sm:text-sm font-medium text-gray-500 uppercase tracking-wide mb-1">
                  Last Name
                </p>
                <p className="text-sm sm:text-base text-gray-900">
                  {userAttributes.family_name || (
                    <span className="text-gray-400 italic">Not set</span>
                  )}
                </p>
              </div>
              <div className="sm:col-span-2">
                <p className="text-xs sm:text-sm font-medium text-gray-500 uppercase tracking-wide mb-1">
                  Position
                </p>
                <p className="text-sm sm:text-base text-gray-900">
                  {userAttributes.position || (
                    <span className="text-gray-400 italic">Not set</span>
                  )}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Account Information */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
          <h2 className="text-lg sm:text-xl font-semibold text-gray-900 mb-6">
            Account Information
          </h2>
          <div className="space-y-4">
            {profileFields.map((field, index) => (
              <div
                key={index}
                className="flex items-start space-x-4 pb-4 border-b border-gray-100 last:border-0 last:pb-0"
              >
                <div className="flex-shrink-0 p-2 bg-primary-50 rounded-lg text-primary-600">
                  {field.icon}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs sm:text-sm font-medium text-gray-500 uppercase tracking-wide">
                    {field.label}
                  </p>
                  <p className="mt-1 text-sm sm:text-base text-gray-900 break-all">
                    {field.value}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Account Settings */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
          <h2 className="text-lg sm:text-xl font-semibold text-gray-900 mb-6">
            Account Settings
          </h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between py-3">
              <div>
                <p className="text-sm sm:text-base font-medium text-gray-900">
                  Password
                </p>
                <p className="text-xs sm:text-sm text-gray-500 mt-1">
                  Change your account password
                </p>
              </div>
              <button className="px-4 py-2 text-sm font-medium text-primary-600 bg-primary-50 rounded-lg hover:bg-primary-100 transition-colors">
                Change
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;
