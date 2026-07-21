// The design-system kit (Phases 2–4). Screens import from here:
//   import { Button, Card, DataTable } from "../../shared/ui";
// The pre-refactor kit still lives in `shared/legacy-ui.tsx` for screens that
// have not been migrated yet.

export { Avatar, type AvatarProps } from "./Avatar/Avatar";
export { Badge, type BadgeProps, type BadgeTone, type BadgeVariant } from "./Badge/Badge";
export { Banner, type BannerProps, type BannerTone } from "./Banner/Banner";
export { Breadcrumb, type BreadcrumbItem, type BreadcrumbProps } from "./Breadcrumb/Breadcrumb";
export { Button, type ButtonProps, type ButtonSize, type ButtonVariant } from "./Button/Button";
export { Card, CardFooter, CardHeader, type CardHeaderProps, type CardProps } from "./Card/Card";
export { BarChart, TrendChart, type ChartProps, type ChartSeries } from "./Chart/Chart";
export { Checkbox, type CheckboxProps } from "./Checkbox/Checkbox";
export { Combobox, type ComboboxOption, type ComboboxProps } from "./Combobox/Combobox";
export { DataState, type DataStateProps } from "./DataState/DataState";
export { DataTable, type DataTableColumn, type DataTableProps } from "./DataTable/DataTable";
export { Modal, type ModalProps } from "./Dialog/Dialog";
export {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  type DropdownMenuItemProps,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./DropdownMenu/DropdownMenu";
export { EmptyState, type EmptyStateProps } from "./EmptyState/EmptyState";
export { ErrorState, type ErrorStateProps } from "./ErrorState/ErrorState";
export { Field, type FieldProps } from "./Field/Field";
export { FormActions, FormGrid, FormSection } from "./Form/Form";
export { errorText, FormModal, type FormModalProps } from "./FormModal/FormModal";
export { Input, type InputProps } from "./Input/Input";
export { KpiCard, type KpiCardProps, type KpiDelta } from "./KpiCard/KpiCard";
export {
  Grid,
  type GridProps,
  Row,
  type RowProps,
  Split,
  type SplitProps,
  Stack,
  type StackProps,
} from "./Layout/Layout";
export { NativeSelect, type NativeSelectProps } from "./NativeSelect/NativeSelect";
export { Pagination, type PaginationProps } from "./Pagination/Pagination";
export { Radio, RadioGroup, type RadioGroupProps, type RadioProps } from "./Radio/Radio";
export { Select, type SelectOption, type SelectProps } from "./Select/Select";
export { Sheet, type SheetProps } from "./Sheet/Sheet";
export { Skeleton, type SkeletonProps } from "./Skeleton/Skeleton";
export { Slider, type SliderProps } from "./Slider/Slider";
export { Spinner, type SpinnerProps } from "./Spinner/Spinner";
export {
  type RailStage,
  StageRail,
  type StageRailProps,
  type StageState,
} from "./StageRail/StageRail";
export { type Step, Stepper, type StepperProps } from "./Stepper/Stepper";
export { Switch, type SwitchProps } from "./Switch/Switch";
export { Tabs, TabsContent, TabsList, TabsTrigger } from "./Tabs/Tabs";
export { Textarea, type TextareaProps } from "./Textarea/Textarea";
export { ToastProvider, type ToastOptions, type ToastTone, useToast } from "./Toast/Toast";
export { Tooltip, type TooltipProps } from "./Tooltip/Tooltip";
