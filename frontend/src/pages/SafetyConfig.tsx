
import React, { useState, useEffect } from "react";
import { configService } from "../services/configService";
// Icons removed to fix dependency issue

// Types
interface ResponsiblePerson {
    name: string;
    phone?: string;
}

interface Project {
    id: string;
    name: string;
    locations: string[];
    responsiblePersons?: ResponsiblePerson[];
}

interface Category {
    code: string;
    name: string;
    category: string;
}

type ConfigOption = string | Project | Category;

// Safe rendering helper to avoid React Error #31
const safeRender = (val: any): string => {
    if (typeof val === 'string' || typeof val === 'number') return String(val);
    return ""; // swallow objects/nulls
};

const CONFIG_TYPES = [
    // { id: "LOCATIONS", label: "Locations (Legacy)" }, // REMOVED as per request
    { id: "PROJECTS", label: "Projects & Locations" },
    { id: "OBSERVATION_TYPES", label: "Observation Types" },
    { id: "BREACH_SOURCES", label: "Breach Sources" },
    { id: "SEVERITY_LEVELS", label: "Severity Levels" },
    { id: "HAZARD_TAXONOMY", label: "Hazard Categories" }
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

    // Responsible Persons Input
    const [newResponsiblePersonName, setNewResponsiblePersonName] = useState("");
    const [newResponsiblePersonPhone, setNewResponsiblePersonPhone] = useState("");
    const [responsiblePersonsList, setResponsiblePersonsList] = useState<ResponsiblePerson[]>([]);

    // Taxonomy Input
    const [newTaxCode, setNewTaxCode] = useState("");
    const [newTaxName, setNewTaxName] = useState("");
    const [newTaxParent, setNewTaxParent] = useState("Safety");

    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        fetchConfig(activeType);
    }, [activeType]);

    const fetchConfig = async (type: string) => {
        setLoading(true);
        try {
            const data = await configService.getConfig(type);
            console.log(`[SafetyConfig] Fetched ${type}:`, data);

            // Validate data is array
            if (!Array.isArray(data)) {
                console.error("[SafetyConfig] Expected array but got:", data);
                setOptions([]);
                return;
            }
            // Sort categories by code if in taxonomy mode
            if (type === "HAZARD_TAXONOMY") {
                const sorted = [...data].sort((a: any, b: any) => {
                    const codeA = a.code || "";
                    const codeB = b.code || "";
                    // Numeric sort for codes like A1, A2, A10 (split alpha and numeric)
                    const letterA = codeA.charAt(0);
                    const letterB = codeB.charAt(0);
                    if (letterA !== letterB) return letterA.localeCompare(letterB);

                    const numA = parseInt(codeA.substring(1)) || 0;
                    const numB = parseInt(codeB.substring(1)) || 0;
                    return numA - numB;
                });
                setOptions(sorted);
            } else {
                setOptions(data || []);
            }

            setError(null);
        } catch (err) {
            console.error(err);
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
    const handleAddResponsiblePerson = () => {
        if (!newResponsiblePersonName.trim()) {
            setError("Person name is required.");
            return;
        }

        const newPerson: ResponsiblePerson = {
            name: newResponsiblePersonName.trim(),
            phone: newResponsiblePersonPhone.trim() || undefined
        };

        setResponsiblePersonsList([...responsiblePersonsList, newPerson]);
        setNewResponsiblePersonName("");
        setNewResponsiblePersonPhone("");
        setError(null);
    };

    const handleRemoveResponsiblePerson = (index: number) => {
        const updated = [...responsiblePersonsList];
        updated.splice(index, 1);
        setResponsiblePersonsList(updated);
    };

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

        // Validate Responsible Persons
        if (responsiblePersonsList.length === 0) {
            setError("At least one responsible person is required.");
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
            locations: locationsList,
            responsiblePersons: responsiblePersonsList
        };

        const updated = [...options, newProject];
        await saveConfig(updated);
        setNewProjectName("");
        setNewProjectLocations("");
        setResponsiblePersonsList([]);
    };

    const handleDeleteProject = async (index: number) => {
        if (!window.confirm("Delete this project and all its locations?")) return;
        const updated = [...options];
        updated.splice(index, 1);
        await saveConfig(updated);
    };

    const handleAddTaxonomyItem = async () => {
        if (!newTaxCode.trim() || !newTaxName.trim()) {
            setError("Code and Name are required.");
            return;
        }

        // Check Duplicates (Code or Name)
        const codeExists = options.some(opt => typeof opt === 'object' && 'code' in opt && (opt as any).code === newTaxCode.trim());
        if (codeExists) {
            setError(`Category with code ${newTaxCode} already exists.`);
            return;
        }

        const newCat = {
            code: newTaxCode.trim(),
            name: newTaxName.trim(),
            category: newTaxParent
        };

        const updated = [...options, newCat];
        await saveConfig(updated);
        setNewTaxCode("");
        setNewTaxName("");
    };

    const handleDeleteTaxonomyItem = async (index: number) => {
        if (!window.confirm("Delete this category?")) return;
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
            console.error(err);
            setError("Failed to save changes.");
        } finally {
            setIsSaving(false);
        }
    };

    const isProjectMode = activeType === "PROJECTS";
    const isTaxonomyMode = activeType === "HAZARD_TAXONOMY";

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
                            {CONFIG_TYPES.find(t => t.id === activeType)?.label || activeType}
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
                                    <div className="bg-white border-2 border-gray-200 rounded-lg shadow-sm overflow-hidden">
                                        <div className="bg-gradient-to-r from-primary-50 to-primary-100 px-6 py-4 border-b border-gray-200">
                                            <h5 className="text-lg font-semibold text-gray-900 flex items-center">
                                                <span className="text-2xl mr-3">🏗️</span>
                                                Add New Project
                                            </h5>
                                        </div>
                                        <div className="p-6 space-y-6">
                                            <div>
                                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                                    Project Name <span className="text-red-500">*</span>
                                                </label>
                                                <input
                                                    type="text"
                                                    value={newProjectName}
                                                    onChange={(e) => setNewProjectName(e.target.value)}
                                                    placeholder="e.g. Riyadh Metro Line 3"
                                                    className="block w-full px-4 py-3 rounded-lg border-2 border-gray-300 shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500 focus:ring-opacity-20 transition-all sm:text-sm"
                                                />
                                            </div>
                                            <div>
                                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                                    Locations <span className="text-red-500">*</span>
                                                </label>
                                                <input
                                                    type="text"
                                                    value={newProjectLocations}
                                                    onChange={(e) => setNewProjectLocations(e.target.value)}
                                                    placeholder="e.g. Main Station, Tunnel A, Storage Yard"
                                                    className="block w-full px-4 py-3 rounded-lg border-2 border-gray-300 shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500 focus:ring-opacity-20 transition-all sm:text-sm"
                                                />
                                                <p className="mt-1 text-xs text-gray-500">Separate multiple locations with commas</p>
                                            </div>

                                            {/* Responsible Persons Section */}
                                            <div className="bg-gray-50 rounded-lg p-5 border-2 border-dashed border-gray-300">
                                                <h6 className="text-sm font-semibold text-gray-900 mb-4 flex items-center">
                                                    <span className="text-xl mr-2">👥</span>
                                                    Responsible Persons
                                                    <span className="ml-2 text-red-500">*</span>
                                                </h6>

                                                <div className="grid grid-cols-1 md:grid-cols-12 gap-3 mb-4">
                                                    <div className="md:col-span-5">
                                                        <label className="block text-xs font-medium text-gray-600 mb-1.5">
                                                            Full Name <span className="text-red-500">*</span>
                                                        </label>
                                                        <input
                                                            type="text"
                                                            value={newResponsiblePersonName}
                                                            onChange={(e) => setNewResponsiblePersonName(e.target.value)}
                                                            placeholder="e.g. Eng. Ahmed"
                                                            className="block w-full px-3 py-2.5 rounded-md border-2 border-gray-300 shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500 focus:ring-opacity-20 transition-all text-sm"
                                                        />
                                                    </div>
                                                    <div className="md:col-span-5">
                                                        <label className="block text-xs font-medium text-gray-600 mb-1.5">
                                                            Phone Number
                                                        </label>
                                                        <input
                                                            type="text"
                                                            value={newResponsiblePersonPhone}
                                                            onChange={(e) => setNewResponsiblePersonPhone(e.target.value)}
                                                            placeholder="e.g. +966 50 123 4567"
                                                            className="block w-full px-3 py-2.5 rounded-md border-2 border-gray-300 shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500 focus:ring-opacity-20 transition-all text-sm"
                                                        />
                                                    </div>
                                                    <div className="md:col-span-2 flex items-end">
                                                        <button
                                                            onClick={handleAddResponsiblePerson}
                                                            type="button"
                                                            className="w-full inline-flex items-center justify-center px-4 py-2.5 border-2 border-primary-600 text-sm font-semibold rounded-md text-primary-700 bg-primary-50 hover:bg-primary-100 transition-colors"
                                                        >
                                                            <span className="text-lg mr-1">+</span>
                                                            Add
                                                        </button>
                                                    </div>
                                                </div>

                                                {/* List of added responsible persons */}
                                                {responsiblePersonsList.length > 0 && (
                                                    <div className="space-y-2 mt-4">
                                                        <p className="text-xs font-medium text-gray-600 mb-2">Added Persons ({responsiblePersonsList.length})</p>
                                                        {responsiblePersonsList.map((person, idx) => (
                                                            <div key={idx} className="flex justify-between items-center bg-white px-4 py-3 rounded-md border-2 border-gray-200 shadow-sm hover:shadow-md transition-shadow">
                                                                <div className="flex items-center space-x-3">
                                                                    <span className="text-lg">👤</span>
                                                                    <div>
                                                                        <p className="text-sm font-semibold text-gray-900">{person.name}</p>
                                                                        {person.phone && (
                                                                            <p className="text-xs text-gray-500 flex items-center mt-0.5">
                                                                                <span className="mr-1">📞</span>
                                                                                {person.phone}
                                                                            </p>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                                <button
                                                                    onClick={() => handleRemoveResponsiblePerson(idx)}
                                                                    type="button"
                                                                    className="px-3 py-1.5 text-xs font-semibold text-red-600 hover:text-white hover:bg-red-600 border-2 border-red-600 rounded-md transition-colors"
                                                                >
                                                                    Remove
                                                                </button>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}

                                                {responsiblePersonsList.length === 0 && (
                                                    <p className="text-xs text-gray-500 italic text-center py-3">No persons added yet. Add at least one responsible person.</p>
                                                )}
                                            </div>

                                            <div className="flex justify-end pt-4 border-t border-gray-200">
                                                <button
                                                    onClick={handleAddProject}
                                                    disabled={isSaving}
                                                    className="inline-flex items-center px-6 py-3 border border-transparent text-sm font-semibold rounded-lg text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-4 focus:ring-primary-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg transition-all"
                                                >
                                                    <span className="text-lg mr-2">✓</span>
                                                    {isSaving ? 'Creating Project...' : 'Create Project'}
                                                </button>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Projects List with Safe Rendering */}
                                    <div className="space-y-4">
                                        {Array.isArray(options) && options.map((opt, idx) => {
                                            // Guard against legacy strings mixed in or nulls
                                            if (typeof opt !== 'object' || opt === null) return null;
                                            const proj = opt as unknown as Project;

                                            // Extra guard: Ensure it looks like a project
                                            if (!proj.id && !proj.name) return null;

                                            return (
                                                <div key={safeRender(proj.id) || idx} className="border rounded-md p-4 hover:shadow-sm transition-shadow">
                                                    <div className="flex justify-between items-start">
                                                        <div className="flex items-center">
                                                            <span className="text-gray-400 mr-3 text-xl">🏢</span>
                                                            <div>
                                                                <h3 className="text-md font-bold text-gray-900">{safeRender(proj.name)}</h3>
                                                                <p className="text-xs text-gray-500">ID: {safeRender(proj.id)}</p>
                                                            </div>
                                                        </div>
                                                        <button
                                                            onClick={() => handleDeleteProject(idx)}
                                                            className="text-red-600 hover:text-red-900 p-1 font-bold"
                                                            title="Delete Project"
                                                            type="button"
                                                        >
                                                            [x]
                                                        </button>
                                                    </div>

                                                    {/* Locations List */}
                                                    <div className="mt-4 pl-9">
                                                        <h6 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                                                            Locations ({Array.isArray(proj.locations) ? proj.locations.length : 0})
                                                        </h6>
                                                        <div className="flex flex-wrap gap-2">
                                                            {Array.isArray(proj.locations) && proj.locations.map((loc, lIdx) => {
                                                                return (
                                                                    <span key={lIdx} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                                                        📍 {safeRender(loc)}
                                                                    </span>
                                                                );
                                                            })}
                                                        </div>
                                                    </div>

                                                    {/* Responsible Persons List */}
                                                    <div className="mt-4 pl-9">
                                                        <h6 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                                                            Responsible Persons ({Array.isArray(proj.responsiblePersons) ? proj.responsiblePersons.length : 0})
                                                        </h6>
                                                        <div className="flex flex-wrap gap-2">
                                                            {Array.isArray(proj.responsiblePersons) && proj.responsiblePersons.map((person, pIdx) => {
                                                                // Handle both old string format and new object format
                                                                const personName = typeof person === 'string' ? person : person.name;
                                                                const personPhone = typeof person === 'object' && person.phone ? person.phone : null;

                                                                return (
                                                                    <span key={pIdx} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                                                        👤 {safeRender(personName)}
                                                                        {personPhone && <span className="text-green-600 ml-1">• {safeRender(personPhone)}</span>}
                                                                    </span>
                                                                );
                                                            })}
                                                        </div>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                            ) : isTaxonomyMode ? (
                                /* --- TAXONOMY MODE --- */
                                <div className="space-y-6">
                                    {/* Add New Category Form */}
                                    <div className="bg-white border-2 border-gray-200 rounded-lg shadow-sm overflow-hidden">
                                        <div className="bg-gradient-to-r from-purple-50 to-blue-100 px-6 py-4 border-b border-gray-200">
                                            <h5 className="text-lg font-semibold text-gray-900 flex items-center">
                                                <span className="text-2xl mr-3">📋</span>
                                                Add New Hazard Category
                                            </h5>
                                        </div>
                                        <div className="p-6">
                                            <div className="grid grid-cols-1 md:grid-cols-12 gap-4">
                                                <div className="md:col-span-3">
                                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                                        Code <span className="text-red-500">*</span>
                                                    </label>
                                                    <input
                                                        type="text"
                                                        value={newTaxCode}
                                                        onChange={(e) => setNewTaxCode(e.target.value)}
                                                        placeholder="e.g. A1"
                                                        className="block w-full px-4 py-3 rounded-lg border-2 border-gray-300 shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500 focus:ring-opacity-20 transition-all sm:text-sm uppercase"
                                                    />
                                                </div>
                                                <div className="md:col-span-6">
                                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                                        Category Name <span className="text-red-500">*</span>
                                                    </label>
                                                    <input
                                                        type="text"
                                                        value={newTaxName}
                                                        onChange={(e) => setNewTaxName(e.target.value)}
                                                        placeholder="e.g. Working at Heights"
                                                        className="block w-full px-4 py-3 rounded-lg border-2 border-gray-300 shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500 focus:ring-opacity-20 transition-all sm:text-sm"
                                                    />
                                                </div>
                                                <div className="md:col-span-3">
                                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                                        Parent Category <span className="text-red-500">*</span>
                                                    </label>
                                                    <select
                                                        value={newTaxParent}
                                                        onChange={(e) => setNewTaxParent(e.target.value)}
                                                        className="block w-full px-4 py-3 rounded-lg border-2 border-gray-300 shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500 focus:ring-opacity-20 transition-all sm:text-sm"
                                                    >
                                                        <option value="Safety">🛡️ Safety</option>
                                                        <option value="Environment">🌍 Environment</option>
                                                        <option value="Health">⚕️ Health</option>
                                                    </select>
                                                </div>
                                            </div>
                                            <div className="flex justify-end mt-6 pt-4 border-t border-gray-200">
                                                <button
                                                    onClick={handleAddTaxonomyItem}
                                                    disabled={isSaving}
                                                    className="inline-flex items-center px-6 py-3 border border-transparent text-sm font-semibold rounded-lg text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-4 focus:ring-primary-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg transition-all"
                                                >
                                                    <span className="text-lg mr-2">✓</span>
                                                    {isSaving ? 'Adding Category...' : 'Add Category'}
                                                </button>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Taxonomy Table */}
                                    <div className="overflow-x-auto border rounded-md">
                                        <table className="min-w-full divide-y divide-gray-200">
                                            <thead className="bg-gray-50">
                                                <tr>
                                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Code</th>
                                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Category Name</th>
                                                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Parent</th>
                                                    <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
                                                </tr>
                                            </thead>
                                            <tbody className="bg-white divide-y divide-gray-200">
                                                {Array.isArray(options) && options.map((opt, idx) => {
                                                    if (typeof opt !== 'object') return null;
                                                    const item = opt as any;
                                                    // Guard: Ensure it's a category
                                                    if (!item.code) return null;

                                                    return (
                                                        <tr key={idx} className="hover:bg-gray-50">
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{safeRender(item.code)}</td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{safeRender(item.name)}</td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${item.category === 'Safety' ? 'bg-green-100 text-green-800' :
                                                                    item.category === 'Environment' ? 'bg-blue-100 text-blue-800' :
                                                                        'bg-purple-100 text-purple-800'
                                                                    }`}>
                                                                    {safeRender(item.category)}
                                                                </span>
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                                                <button
                                                                    onClick={() => handleDeleteTaxonomyItem(idx)}
                                                                    className="text-red-600 hover:text-red-900"
                                                                >
                                                                    Delete
                                                                </button>
                                                            </td>
                                                        </tr>
                                                    );
                                                })}
                                            </tbody>
                                        </table>
                                        {options.length === 0 && (
                                            <p className="p-4 text-center text-gray-500 text-sm">No categories defined.</p>
                                        )}
                                    </div>
                                </div>
                            ) : (
                                /* --- GENERIC LIST MODE --- */
                                <div className="space-y-6">
                                    {/* Add Generic Item */}
                                    <div className="bg-white border-2 border-gray-200 rounded-lg shadow-sm overflow-hidden">
                                        <div className="bg-gradient-to-r from-green-50 to-teal-100 px-6 py-4 border-b border-gray-200">
                                            <h5 className="text-lg font-semibold text-gray-900 flex items-center">
                                                <span className="text-2xl mr-3">➕</span>
                                                Add New Item
                                            </h5>
                                        </div>
                                        <div className="p-6">
                                            <div className="flex gap-3">
                                                <div className="flex-1">
                                                    <input
                                                        type="text"
                                                        value={newItem}
                                                        onChange={(e) => setNewItem(e.target.value)}
                                                        onKeyDown={(e) => e.key === 'Enter' && handleAddGenericItem()}
                                                        placeholder="Enter option name..."
                                                        className="block w-full px-4 py-3 rounded-lg border-2 border-gray-300 shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-500 focus:ring-opacity-20 transition-all sm:text-sm"
                                                        disabled={isSaving}
                                                    />
                                                </div>
                                                <button
                                                    onClick={handleAddGenericItem}
                                                    disabled={!newItem.trim() || isSaving}
                                                    className="inline-flex items-center px-6 py-3 border border-transparent text-sm font-semibold rounded-lg text-white bg-primary-600 hover:bg-primary-700 focus:outline-none focus:ring-4 focus:ring-primary-500 focus:ring-opacity-20 disabled:opacity-50 disabled:cursor-not-allowed shadow-md hover:shadow-lg transition-all"
                                                >
                                                    <span className="text-lg mr-2">✓</span>
                                                    Add
                                                </button>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Generic List */}
                                    <ul className="divide-y divide-gray-200 border rounded-md">
                                        {options.length === 0 ? (
                                            <li className="px-4 py-4 text-center text-gray-500 text-sm">No options defined.</li>
                                        ) : (
                                            Array.isArray(options) && options.map((opt, idx) => {
                                                if (typeof opt !== 'string') return null; // Skip objects in string mode
                                                return (
                                                    <li key={idx} className="flex justify-between items-center px-4 py-3 hover:bg-gray-50">
                                                        <span className="text-sm text-gray-700">{safeRender(opt)}</span>
                                                        <button
                                                            onClick={() => handleDeleteGenericItem(idx)}
                                                            disabled={isSaving}
                                                            className="text-red-600 hover:text-red-900 text-sm font-bold"
                                                            title="Delete"
                                                            type="button"
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
