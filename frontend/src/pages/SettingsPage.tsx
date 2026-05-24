import type { DbConnection, TableCatalog } from "@shared/types";
import { ConnectionSettings } from "@features/settings/ConnectionSettings";

type Props = {
  connections: DbConnection[];
  tables: TableCatalog[];
  onCreate: (name: string, description: string, url: string, schema: string) => Promise<void>;
  onIntrospect: (connectionId: string) => Promise<void>;
  onWritePolicy: (
    connectionId: string,
    enabled: boolean,
    schemas: string[],
    confirmed?: boolean,
  ) => Promise<void>;
  t: (key: string) => string;
};

export function SettingsPage({ connections, tables, onCreate, onIntrospect, onWritePolicy, t }: Props) {
  return (
    <ConnectionSettings
      connections={connections}
      tables={tables}
      onCreate={onCreate}
      onIntrospect={onIntrospect}
      onWritePolicy={onWritePolicy}
      t={t}
    />
  );
}
