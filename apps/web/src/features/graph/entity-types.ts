/** How each entity type is named and coloured. The API may add types; unknown ones are grey. */

type TypeStyle = { label: string; plural: string; fill: string; dot: string };

const STYLES: Record<string, TypeStyle> = {
  code: { label: "Code", plural: "Codes", fill: "fill-amber-500", dot: "bg-amber-500" },
  name: { label: "Name", plural: "Names", fill: "fill-sky-600", dot: "bg-sky-600" },
  person: { label: "Person", plural: "People", fill: "fill-rose-500", dot: "bg-rose-500" },
  organization: {
    label: "Organization",
    plural: "Organizations",
    fill: "fill-violet-500",
    dot: "bg-violet-500",
  },
  place: { label: "Place", plural: "Places", fill: "fill-emerald-600", dot: "bg-emerald-600" },
  product: { label: "Product", plural: "Products", fill: "fill-teal-500", dot: "bg-teal-500" },
  concept: { label: "Concept", plural: "Concepts", fill: "fill-indigo-400", dot: "bg-indigo-400" },
};

const FALLBACK: TypeStyle = {
  label: "Other",
  plural: "Other",
  fill: "fill-slate-400",
  dot: "bg-slate-400",
};

export function entityType(type: string): TypeStyle {
  return STYLES[type] ?? FALLBACK;
}

export function entityPath(id: string): string {
  return `/graph/entities/${id}`;
}

export function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}
