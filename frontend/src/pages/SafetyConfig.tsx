
import React, { useState, useEffect } from "react";
import { configService } from "../services/configService";


const CONFIG_TYPES = [
    { id: "LOCATIONS", label: "Locations" },
    { id: "OBSERVATION_TYPES", label: "Observation Types" },
    { id: "BREACH_SOURCES", label: "Breach Sources" },
    { id: "SEVERITY_LEVELS", label: "Severity Levels" }
];

const SafetyConfig: React.FC = () => {
    const [activeType, setActiveType] = useState("LOCATIONS");
    const [options, setOptions] = useState<string[]>([]);
    const [loading, setLoading] = useState(false);
    const [newItem, setNewItem] = useState("");
    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        fetchConfig(activeType);
    }, [activeType]);

    const fetchConfig = async (type: string) => {
        setLoading(true);
        try {
            const data = await configService.getConfig(type);
            setOptions(data || []);
            setError(null);
        } catch (err) {
            setError("Failed to load configuration.");
        } finally {
            setLoading(false);
        }
    };

    const handleAddItem = async () => {
        if (!newItem.trim()) return;
        if (options.includes(newItem.trim())) {
            setError("Item already exists.");
            return;
        }

        const updated = [...options, newItem.trim()];
        await saveConfig(updated);
        setNewItem("");
    };

    const handleDeleteItem = async (index: number) => {
        if (!window.confirm("Are you sure you want to remove this option?")) return;
        const updated = [...options];
        updated.splice(index, 1);
        await saveConfig(updated);
    };

    const saveConfig = async (updatedOptions: string[]) => {
        setIsSaving(true);
        try {
            await configService.updateConfig(activeType, updatedOptions);
            setOptions(updatedOptions);
            setError(null);
        } catch (err) {
            setError("Failed to save changes.");
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="border-b border-gray-200 pb-5">
                <h3 className="text-2xl font-bold leading-6 text-gray-900">
                    Safety Workflow Configuration
                </h3>
                <p className="mt-2 text-sm text-gray-500">
                    Manage dropdown options for the WhatsApp Safety Agent.
                </p>
            </div>

            <div className="flex flex-col md:flex-row gap-6">
                {/* Sidebar for Types */}
                <div className="w-full md:w-64 flex-shrink-0">
                    <nav className="space-y-1">
                        {CONFIG_TYPES.map((type) => (
                            <button
                                key={type.id}
                                onClick={() => setActiveType(type.id)}
                                className={`w-full flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors ${activeType === type.id
                                    ? "bg-primary-50 text-primary-700"
                                    : "text-gray-900 hover:bg-gray-50 hover:text-gray-900"
                                    }`}
                            >
                                {type.label}
                            </button>
                        ))}
                    </nav>
                </div>

                {/* Content Area */}
                <div className="flex-1 bg-white shadow rounded-lg p-6">
                    <div className="flex justify-between items-center mb-6">
                        <h4 className="text-lg font-medium text-gray-900">
                            {CONFIG_TYPES.find(t => t.id === activeType)?.label}
                        </h4>
                        <span className="text-xs text-gray-400">PK: CONFIG, SK: {activeType}</span>
                    </div>

                    {error && (
                        <div className="mb-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
                            {error}
                        </div>
                    )}

                    {loading ? (
                        <div className="flex justify-center py-10">
                            <svg className="animate-spin h-8 w-8 text-primary-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                        </div>
                    ) : (
                        <>
                            {/* Add New Item */}
                            <div className="flex gap-2 mb-6">
                                <input
                                    type="text"
                                    value={newItem}
                                    onChange={(e) => setNewItem(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleAddItem()}
                                    placeholder="Add new option..."
                                    className="flex-1 rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                                    disabled={isSaving}
                                />
                                <button
                                    onClick={handleAddItem}
                                    disabled={!newItem.trim() || isSaving}
                                    className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500 disabled:opacity-50"
                                >
                                    {isSaving ? "Saving..." : "Add"}
                                </button>
                            </div>

                            {/* List */}
                            <ul className="divide-y divide-gray-200 border rounded-md">
                                {options.length === 0 ? (
                                    <li className="px-4 py-4 text-center text-gray-500 text-sm">No options defined.</li>
                                ) : (
                                    options.map((opt, idx) => (
                                        <li key={idx} className="flex justify-between items-center px-4 py-3 hover:bg-gray-50">
                                            <span className="text-sm text-gray-700">{opt}</span>
                                            <button
                                                onClick={() => handleDeleteItem(idx)}
                                                disabled={isSaving}
                                                className="text-red-600 hover:text-red-900 text-sm"
                                                title="Delete"
                                            >
                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                </svg>
                                            </button>
                                        </li>
                                    ))
                                )}
                            </ul>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};

export default SafetyConfig;
