/**
 * Architecture V2 Product Experience Architecture - Wave 1 contract barrel.
 *
 * These modules are the machine-readable form of
 * `docs/engineering/Architecture-V2/04_PRODUCT_EXPERIENCE_ARCHITECTURE.md`:
 * shell regions, workspace patterns, panel taxonomy, the canonical Inspector, action
 * geography, canonical AI actions, the command palette and the Active Context
 * contract, plus the composition-only work-mode registry.
 *
 * The barrel is the single import point for a surface that wants to compose
 * according to the contract, so a Wave 9 migration does not have to reach into
 * individual files. Nothing here grants authority, renders UI or calls the backend.
 */

export {
  AI_ACTION_KINDS,
  ACTION_PLACEMENTS,
  INSPECTOR_SUBJECT_KINDS,
  PANEL_KINDS,
  SHELL_REGIONS,
  WORKSPACE_PATTERNS,
  aiActionLabelKey,
  isActionPlacement,
  isAiActionKind,
  isInspectorSubjectKind,
  isPanelKind,
  isShellRegion,
  isWorkspacePattern,
  panelKindLabelKey,
  shellRegionLabelKey,
  workspacePatternLabelKey,
  type ActionPlacement,
  type AiActionKind,
  type InspectorSubjectKind,
  type PanelKind,
  type ShellRegion,
  type WorkspacePattern,
} from "./vocabulary.ts";

export {
  plannedShellRegions,
  renderedShellRegions,
  shellRegionContract,
  shellRegionCoverage,
  shellRegions,
  type ShellRegionContract,
  type ShellRegionImplementation,
} from "./shellContract.ts";

export {
  compositionForPage,
  compositionOwner,
  headerModeForPage,
  inspectorSubjectsForPage,
  registeredPages,
  taskPatternFor,
  taskPatterns,
  usesConsolidatedHeader,
  workspaceCompositions,
  workspacePatternForPage,
  type WorkspaceComposition,
  type WorkspaceHeaderMode,
} from "./workspacePatterns.ts";

export {
  DISCLOSURE_KINDS,
  panelContract,
  panelKindsForPattern,
  panelTaxonomy,
  panelsWithSharedOwner,
  requiredDisclosures,
  unownedPanelKinds,
  type DisclosureKind,
  type PanelContract,
  type PanelImplementation,
} from "./panelTaxonomy.ts";

export {
  ACTION_CONSEQUENCES,
  GUARDED_CONSEQUENCES,
  PRIMARY_SLOT_CONSEQUENCES,
  actionGeography,
  actionGeographyRule,
  actionPlacement,
  detailPlacement,
  mayOccupyPrimarySlot,
  requiresDeliberateStep,
  type ActionConsequence,
  type ActionGeographyRule,
} from "./actionGeography.ts";

export {
  AI_INVARIANTS,
  aiActionContract,
  aiActionIsAvailable,
  aiActions,
  aiInvariantHolds,
  declaredAiActions,
  type AiActionContract,
  type AiActionPosture,
  type AiInvariant,
} from "./aiActions.ts";

export {
  EMPTY_INSPECTOR_STATE,
  INSPECTOR_HISTORY_LIMIT,
  canOpenInspector,
  inspectorIsOpen,
  inspectorMatchesPage,
  inspectorReducer,
  openInspector,
  type InspectorEvent,
  type InspectorState,
  type InspectorSubject,
} from "./inspectorContract.ts";

export {
  ACTIVE_CONTEXT_GAPS,
  ACTIVE_CONTEXT_QUERY_KEYS,
  activeContextFromParts,
  activeContextGapOwner,
  activeContextGaps,
  activeContextIsReproducible,
  activeContextKey,
  activeContextSummary,
  type ActiveContext,
  type ActiveContextGap,
  type ActiveContextParts,
} from "./activeContext.ts";

export {
  WORK_MODE_GRANTS_AUTHORITY,
  WORK_MODE_IDS,
  modeEmphasisFor,
  modeEmphasizes,
  workModeComposition,
  workModes,
  type WorkModeComposition,
  type WorkModeId,
} from "./workModes.ts";

export {
  ADMINISTRATION_CAPABILITIES,
  SERVER_WORK_MODE_IDS,
  availableModeCompositions,
  compositionAllowsMode,
  compositionFromProfile,
  compositionHasCommercialAccess,
  compositionHoldsCapability,
  compositionSeesAdministration,
  type ClientExperienceComposition,
} from "./experienceProfile.ts";

export {
  apiErrorBodyFrom,
  describeApiError,
  describeFailure,
  errorFamilyIds,
  isRetryable,
  pickApiErrorBody,
  presentError,
  requiresUserAction,
  type ApiErrorBody,
  type ErrorFamilyId,
  type ErrorPresentation,
  type ErrorText,
  type Translate,
} from "./errorPresentation.ts";

export {
  DEFAULT_PALETTE_LIMIT,
  aiCommands,
  buildPaletteCommands,
  commandById,
  filterPaletteCommands,
  inspectionCommands,
  isPaletteDismissKey,
  isPaletteShortcut,
  navigationCommands,
  paletteCommandAvailable,
  paletteUnavailableReasonKey,
  utilityCommands,
  type PaletteAvailability,
  type PaletteCommand,
  type PaletteCommandGroup,
  type PaletteKeyEvent,
} from "./commandPalette.ts";
