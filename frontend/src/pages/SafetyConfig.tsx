
import React, { useState, useEffect } from "react";
import { configService } from "../services/configService";
// Icons removed to fix dependency issue

// Types
interface Project {
    id: string;
    name: string;
    locations: string[];
}

type ConfigOption = string | Project;

const CONFIG_TYPES = [
    { id: "LOCATIONS", label: "Locations (Legacy)" }, // Kept for reference or simple lists if needed
    { id: "OBSERVATION_TYPES", label: "Observation Types" },
    { id: "BREACH_SOURCES", label: "Breach Sources" },
    { id: "SEVERITY_LEVELS", label: "Severity Levels" },
    { id: "PROJECTS", label: "Projects & Locations" }
];

const SafetyConfig: React.FC = () => {
    const [activeType, setActiveType] = useState("PROJECTS"); // Default to Projects
    const [options, setOptions] = useState<ConfigOption[]>([]);
    const [loading, setLoading] = useState(false);

    // Generic Input
    const [newItem, setNewItem] = useState("");

    // Project Input
    const [newProjectName, setNewProjectName] = useState("");
    const [newProjectLocations, setNewProjectLocations] = useState<string>(""); // Comma separated for simplicity

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

    // --- GENERIC HANDLERS (Strings) ---
    const handleAddGenericItem = async () => {
        if (!newItem.trim()) return;
        if (options.some(opt => typeof opt === 'string' && opt === newItem.trim())) {
            setError("Item already exists.");
            return;
        }

        const updated = [...options, newItem.trim()];
        await saveConfig(updated);
        setNewItem("");
    };

    const handleDeleteGenericItem = async (index: number) => {
        if (!window.confirm("Are you sure you want to remove this option?")) return;
        const updated = [...options];
        updated.splice(index, 1);
        await saveConfig(updated);
    };

    // --- PROJECT HANDLERS (Objects) ---
    const handleAddProject = async () => {
        if (!newProjectName.trim()) {
            setError("Project Name is required.");
            return;
        }

        // Validate Locations
        const locationsList = newProjectLocations.split(",").map(s => s.trim()).filter(Boolean);
        if (locationsList.length === 0) {
            setError("At least one location is required.");
            return;
        }

        // Duplicate Check
        if (options.some(opt => typeof opt === 'object' && opt.name.toLowerCase() === newProjectName.trim().toLowerCase())) {
            setError("Project with this name already exists.");
            return;
        }

        const newProject: Project = {
            id: `PROJ-${Date.now()}`, // Simple ID gen
            name: newProjectName.trim(),
            locations: locationsList
        };

        const updated = [...options, newProject];
        await saveConfig(updated);
        setNewProjectName("");
        setNewProjectLocations("");
    };

    const handleDeleteProject = async (index: number) => {
        if (!window.confirm("Delete this project and all its locations?")) return;
        const updated = [...options];
        updated.splice(index, 1);
        await saveConfig(updated);
    };

    const saveConfig = async (updatedOptions: ConfigOption[]) => {
        setIsSaving(true);
        try {
            // Service expects any[] so this is fine
            await configService.updateConfig(activeType, updatedOptions as any[]);
            setOptions(updatedOptions);
            setError(null);
        } catch (err) {
            setError("Failed to save changes.");
        } finally {
            setIsSaving(false);
        }
    };

    const isProjectMode = activeType === "PROJECTS";

    return (
        <div className="space-y-6">
            <div className="border-b border-gray-200 pb-5">
                <h3 className="text-2xl font-bold leading-6 text-gray-900">
                    Safety Workflow Configuration
                </h3>
                <p className="mt-2 text-sm text-gray-500">
                    Manage dropdown options and Project sites for the WhatsApp Assistant.
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
                            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
                        </div>
                    ) : (
                        <>
                            {/* --- COMPONENT SWITCH --- */}
                            {isProjectMode ? (
                                <div className="space-y-6">
                                    {/* Add New Project Form */}
                                    <div className="bg-gray-50 p-4 rounded-md border border-gray-200 space-y-4">
                                        <h5 className="text-sm font-medium text-gray-700">Add New Project</h5>
                                        <div className="grid grid-cols-1 gap-4">
                                            <input
                                                type="text"
                                                value={newProjectName}
                                                onChange={(e) => setNewProjectName(e.target.value)}
                                                placeholder="Project Name (e.g. Riyadh Metro)"
                                                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                                            />
                                            <input
                                                type="text"
                                                value={newProjectLocations}
                                                onChange={(e) => setNewProjectLocations(e.target.value)}
                                                placeholder="Locations (comma separated, e.g. Main Station, Tunnel A)"
                                                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                                            />
                                            <div className="flex justify-end">
                                                <button
                                                    onClick={handleAddProject}
                                                    disabled={isSaving}
                                                    className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                                                >
                                                    [+] Add Project
                                                </button>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Projects List */}
                                    <div className="space-y-4">
                                        {options.map((opt, idx) => {
                                            // Guard against legacy strings mixed in
                                            if (typeof opt !== 'object') return null;
                                            const proj = opt as Project;
                                            return (
                                                <div key={proj.id || idx} className="border rounded-md p-4 hover:shadow-sm transition-shadow">
                                                    <div className="flex justify-between items-start">
                                                        <div className="flex items-center">
                                                            <span className="text-gray-400 mr-3 text-xl">🏢</span>
                                                            <div>
                                                                <h3 className="text-md font-bold text-gray-900">{proj.name}</h3>
                                                                <p className="text-xs text-gray-500">ID: {proj.id}</p>
                                                            </div>
                                                        </div>
                                                        <button
                                                            onClick={() => handleDeleteProject(idx)}
                                                            className="text-red-600 hover:text-red-900 p-1 font-bold"
                                                            title="Delete Project"
                                                        >
                                                            [x]
                                                        </button>
                                                    </div>

                                                    {/* Locations List */}
                                                    <div className="mt-4 pl-9">
                                                        <h6 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                                                            Locations ({proj.locations.length})
                                                        </h6>
                                                        <div className="flex flex-wrap gap-2">
                                                            {proj.locations.map((loc, lIdx) => (
                                                                <span key={lIdx} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                                                    📍 {loc}
                                                                </span>
                                                            ))}
                                                        </div>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            ) : (
                                /* --- GENERIC LIST MODE --- */
                                <div className="space-y-6">
                                    {/* Add Generic Item */}
                                    <div className="flex gap-2">
                                        <input
                                            type="text"
                                            value={newItem}
                                            onChange={(e) => setNewItem(e.target.value)}
                                            onKeyDown={(e) => e.key === 'Enter' && handleAddGenericItem()}
                                            placeholder="Add new option..."
                                            className="flex-1 rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                                            disabled={isSaving}
                                        />
                                        <button
                                            onClick={handleAddGenericItem}
                                            disabled={!newItem.trim() || isSaving}
                                            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-50"
                                        >
                                            [+] Add
                                        </button>
                                    </div>

                                    {/* Generic List */}
                                    <ul className="divide-y divide-gray-200 border rounded-md">
                                        {options.length === 0 ? (
                                            <li className="px-4 py-4 text-center text-gray-500 text-sm">No options defined.</li>
                                        ) : (
                                            options.map((opt, idx) => {
                                                if (typeof opt !== 'string') return null; // Skip objects in string mode
                                                return (
                                                    <li key={idx} className="flex justify-between items-center px-4 py-3 hover:bg-gray-50">
                                                        <span className="text-sm text-gray-700">{opt}</span>
                                                        <button
                                                            onClick={() => handleDeleteGenericItem(idx)}
                                                            disabled={isSaving}
                                                            className="text-red-600 hover:text-red-900 text-sm font-bold"
                                                            title="Delete"
                                                        >
                                                            [x]
                                                        </button>
                                                    </li>
                                                );
                                            })
                                        )}
                                    </ul>
                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
};

export default SafetyConfig;
