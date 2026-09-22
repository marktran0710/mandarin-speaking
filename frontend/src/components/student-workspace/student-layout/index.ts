export {
  StudentActionBar,
  StudentCluster,
  StudentGrid,
  StudentPageBody,
  StudentRow,
  StudentStack,
} from "./StudentLayoutPrimitives";
export type {
  StudentActionAlignment,
  StudentGridColumns,
  StudentLayoutDensity,
  StudentPageBodyVariant,
} from "./StudentLayoutPrimitives";

// The section primitive remains implemented in its existing domain folder;
// this barrel exposes the complete Student Mode layout vocabulary from one
// public boundary without creating a second implementation.
export {
  StudentSection,
  StudentSectionBody,
  StudentSectionFooter,
  StudentSectionHeader,
} from "../student-section";
export type {
  StudentSectionBodyLayout,
  StudentSectionDensity,
  StudentSectionVariant,
} from "../student-section";
