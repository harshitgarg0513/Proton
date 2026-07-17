import { Card, CardContent } from "@/components/ui/card";

interface StatCardProps {
  title: string;
  value: string | number | null | undefined;
  subtitle?: string;
}

export default function StatCard({
  title,
  value,
  subtitle,
}: StatCardProps) {
  const display =
    value === null ||
    value === undefined ||
    value === "" ||
    value === "N/A"
      ? "-"
      : value;

  return (
    <Card className="border bg-card">
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground">{title}</p>

        <h3 className="mt-2 text-xl font-semibold break-words">
          {display}
        </h3>

        {subtitle && (
          <p className="mt-1 text-xs text-muted-foreground">
            {subtitle}
          </p>
        )}
      </CardContent>
    </Card>
  );
}