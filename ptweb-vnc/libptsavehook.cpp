#define _GNU_SOURCE
#include <dlfcn.h>
#include <QString>
#include <QStringList>
#include <QWidget>
#include <QFileDialog>
#include <QDir>
#include <QFileInfo>

typedef QString (*SaveFileNameFunc)(QWidget *, const QString &, const QString &, const QString &, QString *, QFlags<QFileDialog::Option>);
typedef QString (*OpenFileNameFunc)(QWidget *, const QString &, const QString &, const QString &, QString *, QFlags<QFileDialog::Option>);
typedef QStringList (*OpenFileNamesFunc)(QWidget *, const QString &, const QString &, const QString &, QString *, QFlags<QFileDialog::Option>);
typedef QString (*ExistingDirFunc)(QWidget *, const QString &, const QString &, QFlags<QFileDialog::Option>);

static SaveFileNameFunc real_getSaveFileName = nullptr;
static OpenFileNameFunc real_getOpenFileName = nullptr;
static OpenFileNamesFunc real_getOpenFileNames = nullptr;
static ExistingDirFunc real_getExistingDir = nullptr;

static inline QString get_effective_dir(const QString &dir) {
    const QString target = QStringLiteral("/home/ptuser/Desktop/Personal_Saves");
    if (dir.isEmpty() || dir == QStringLiteral("/") || dir == QStringLiteral("/tmp") ||
        dir == QStringLiteral("/home/ptuser") || dir == QStringLiteral("/home/ptuser/")) {
        return target;
    }
    QString d = dir;
    if (d.contains(QStringLiteral("/home/ptuser/pt/saves"))) {
        d.replace(QStringLiteral("/home/ptuser/pt/saves"), target);
        return d;
    }
    if (d.contains(QStringLiteral("pt/saves"))) {
        d.replace(QStringLiteral("pt/saves"), QStringLiteral("Desktop/Personal_Saves"));
        return d;
    }
    if (d.contains(QStringLiteral("Saved_Files"))) {
        d.replace(QStringLiteral("Saved_Files"), QStringLiteral("Personal_Saves"));
        return d;
    }
    return d;
}

QString QFileDialog::getSaveFileName(QWidget *parent,
                                    const QString &caption,
                                    const QString &dir,
                                    const QString &filter,
                                    QString *selectedFilter,
                                    QFlags<QFileDialog::Option> options)
{
    if (!real_getSaveFileName) {
        real_getSaveFileName = (SaveFileNameFunc)dlsym(RTLD_NEXT, "_ZN11QFileDialog15getSaveFileNameEP7QWidgetRK7QStringS4_S4_PS2_6QFlagsINS_6OptionEE");
    }
    QString effective = get_effective_dir(dir);
    return real_getSaveFileName(parent, caption, effective, filter, selectedFilter, options);
}

QString QFileDialog::getOpenFileName(QWidget *parent,
                                    const QString &caption,
                                    const QString &dir,
                                    const QString &filter,
                                    QString *selectedFilter,
                                    QFlags<QFileDialog::Option> options)
{
    if (!real_getOpenFileName) {
        real_getOpenFileName = (OpenFileNameFunc)dlsym(RTLD_NEXT, "_ZN11QFileDialog15getOpenFileNameEP7QWidgetRK7QStringS4_S4_PS2_6QFlagsINS_6OptionEE");
    }
    QString effective = get_effective_dir(dir);
    return real_getOpenFileName(parent, caption, effective, filter, selectedFilter, options);
}

QStringList QFileDialog::getOpenFileNames(QWidget *parent,
                                        const QString &caption,
                                        const QString &dir,
                                        const QString &filter,
                                        QString *selectedFilter,
                                        QFlags<QFileDialog::Option> options)
{
    if (!real_getOpenFileNames) {
        real_getOpenFileNames = (OpenFileNamesFunc)dlsym(RTLD_NEXT, "_ZN11QFileDialog16getOpenFileNamesEP7QWidgetRK7QStringS4_S4_PS2_6QFlagsINS_6OptionEE");
    }
    QString effective = get_effective_dir(dir);
    return real_getOpenFileNames(parent, caption, effective, filter, selectedFilter, options);
}

QString QFileDialog::getExistingDirectory(QWidget *parent,
                                         const QString &caption,
                                         const QString &dir,
                                         QFlags<QFileDialog::Option> options)
{
    if (!real_getExistingDir) {
        real_getExistingDir = (ExistingDirFunc)dlsym(RTLD_NEXT, "_ZN11QFileDialog20getExistingDirectoryEP7QWidgetRK7QStringS4_6QFlagsINS_6OptionEE");
    }
    QString effective = get_effective_dir(dir);
    return real_getExistingDir(parent, caption, effective, options);
}
