import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api.js";

export default function DocumentSidebar() {
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState(null);
  const [entityName, setEntityName] = useState("");
  const [entityAliases, setEntityAliases] = useState("");
  const fileInputRef = useRef(null);

  const loadDocuments = async () => {
    try {
      const data = await api.get("/documents");
      setDocuments(Array.isArray(data) ? data : data.documents || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    loadDocuments();
  }, []);

  const handleUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setUploading(true);
    setStatus(null);
    try {
      for (const file of files) {
        const formData = new FormData();
        formData.append("file", file);
        if (entityName.trim()) formData.append("entity_name", entityName.trim());
        if (entityAliases.trim()) formData.append("entity_aliases", entityAliases.trim());
        const result = await api.postForm("/documents", formData);
        setStatus(
          result.embedding_status === "lexical_only"
            ? `${file.name} uploaded${result.entity?.display_name ? ` for ${result.entity.display_name}` : ""}. Semantic embeddings are offline, so search is lexical-only for now.`
            : `${file.name} uploaded successfully${result.entity?.display_name ? ` for ${result.entity.display_name}` : ""}.`
        );
      }
      await loadDocuments();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/documents/${id}`);
      setDocuments((prev) => prev.filter((d) => d.document_id !== id));
      setStatus("Document removed.");
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <h2 className="font-display text-sm font-semibold uppercase tracking-wide text-slate mb-3">
        Documents
      </h2>

      <div className="block">
        <input
          value={entityName}
          onChange={(e) => setEntityName(e.target.value)}
          placeholder="Participant or entity name"
          className="w-full mb-2 rounded-md border border-slate-200 px-3 py-2 text-sm"
        />
        <input
          value={entityAliases}
          onChange={(e) => setEntityAliases(e.target.value)}
          placeholder="Aliases, comma separated"
          className="w-full mb-2 rounded-md border border-slate-200 px-3 py-2 text-sm"
        />
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleUpload}
          className="hidden"
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="block w-full text-center text-sm font-medium text-teal-700 border border-dashed border-teal-500/50 rounded-md py-3 cursor-pointer hover:bg-teal-50 transition-colors"
        >
          {uploading ? "Uploading…" : "Upload documents"}
        </button>
      </div>

      {error && (
        <p className="text-xs text-ochre-600 mt-2 font-mono">{error}</p>
      )}

      {status && (
        <p className="text-xs text-teal-700 mt-2">{status}</p>
      )}

      <ul className="mt-4 space-y-1 overflow-y-auto flex-1">
        {documents.map((doc) => (
          <li
            key={doc.document_id}
            className="group px-2 py-2 rounded-sm hover:bg-teal-50"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm truncate" title={doc.name}>
                  {doc.name}
                </div>
                <div className="text-[11px] text-slate mt-0.5">
                  {doc.records_count} records · {doc.chunks_count} chunks
                </div>
                {doc.entity_names?.length ? (
                  <div className="text-[11px] text-teal-700 mt-0.5 truncate">
                    {doc.entity_names.join(", ")}
                  </div>
                ) : null}
              </div>
              <button
                onClick={() => handleDelete(doc.document_id)}
                aria-label={`Delete ${doc.name}`}
                className="text-slate hover:text-red-600 text-xs opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
              >
                Remove
              </button>
            </div>
          </li>
        ))}
        {!documents.length && !error && (
          <li className="text-sm text-slate italic px-2">
            No documents yet
          </li>
        )}
      </ul>
    </div>
  );
}
