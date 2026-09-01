import { useEffect, useState } from "react";
import { getFileImpact } from "../services/api";

export default function ImpactPanel({ projectId, filePath, onSelectFile }) {
  const [impact, setImpact] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!projectId || !filePath) {
      setImpact(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getFileImpact(projectId, filePath)
      .then((data) => {
        if (!cancelled) setImpact(data);
      })
      .catch(() => {
        if (!cancelled) setImpact(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, filePath]);

  if (!filePath) return null;

  return (
    <div className="px-4 py-4 border-t border-ink-700">
      <h3 className="font-display text-[12px] font-medium text-parchment-300">
        Change impact
      </h3>

      {loading && <p className="mt-2 text-[12px] text-parchment-700">Checking...</p>}

      {!loading && impact && (
        <>
          <p className="mt-2 text-[13px] text-parchment-300">
            Changing this file could affect{" "}
            <span className="font-mono text-parchment-100">{impact.estimatedAffected}</span>{" "}
            other {impact.estimatedAffected === 1 ? "file" : "files"}.
          </p>

          <ImpactGroup
            label="Directly imports it"
            files={impact.directDependents}
            onSelectFile={onSelectFile}
          />
          <ImpactGroup
            label="Affected indirectly"
            files={impact.indirectDependents}
            onSelectFile={onSelectFile}
          />
        </>
      )}
    </div>
  );
}

function ImpactGroup({ label, files, onSelectFile }) {
  if (files.length === 0) return null;
  return (
    <div className="mt-3">
      <p className="text-[11px] text-parchment-500">{label}</p>
      <ul className="mt-1 space-y-0.5">
        {files.map((fileId) => (
          <li key={fileId}>
            <button
              onClick={() => onSelectFile(fileId)}
              className="w-full text-left truncate font-mono text-[12px] text-parchment-300 hover:text-brass-400 px-1.5 py-0.5 rounded-sm hover:bg-ink-800"
            >
              {fileId}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
