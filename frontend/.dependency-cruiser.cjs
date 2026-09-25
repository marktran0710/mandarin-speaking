module.exports = {
	forbidden: [
		{
			name: "no-circular",
			comment: "Dependencies must form an acyclic graph.",
			severity: "error",
			from: {},
			to: { circular: true },
		},
		{
			name: "not-to-unresolvable",
			comment: "Every imported module must resolve.",
			severity: "error",
			from: {},
			to: { couldNotResolve: true },
		},
		{
			name: "no-orphans",
			comment: "Every source module must be reachable from an application or test entrypoint.",
			severity: "error",
			from: { orphan: true, pathNot: "(^|/)\\.[^/]+\\.(?:js|cjs|mjs|ts|json)$|\\.d\\.(?:c|m)?ts$|(^|/)tsconfig\\.json$|^src/entities/.*/types\\.ts$|^src/entities/.*/index\\.ts$|^src/(?:app/appTypes\\.ts|types/[^/]+\\.ts|helpers/helpRequests\\.ts|utils/pilotSession\\.ts|components/pronunciation-breakdown/types\\.ts)$" },
			to: {},
		},
		{
			name: "no-shared-to-higher-layer",
			comment: "shared cannot depend on entities, features, or app.",
			severity: "error",
			from: { path: "^src/shared(?:/|$)" },
			to: { path: "^src/(?:entities|features|app)(?:/|$)" },
		},
		{
			name: "no-entities-to-higher-layer",
			comment: "entities cannot depend on features or app.",
			severity: "error",
			from: { path: "^src/entities(?:/|$)" },
			to: { path: "^src/(?:features|app)(?:/|$)" },
		},
		{
			name: "no-features-to-app",
			comment: "features cannot depend on app shells or entrypoints.",
			severity: "error",
			from: { path: "^src/features(?:/|$)" },
			to: { path: "^src/app(?:/|$)" },
		},
	],
	options: {
		doNotFollow: { path: "node_modules" },
		tsConfig: { fileName: "tsconfig.json" },
	},
};
