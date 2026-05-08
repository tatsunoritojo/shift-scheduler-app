import { api, getCurrentUser } from './modules/api-client.js';
import { showToast } from './modules/notification.js';
import { renderCalendar } from './modules/calendar-grid.js';
import { timeToMinutes, minutesToTime } from './modules/time-utils.js';
import { escapeHtml } from './modules/escape-html.js';
import { showConfirmDialog } from './modules/ui-dialogs.js';
import { setLoading, withLoading } from './modules/btn-loading.js';
import { isAllDayEvent, getEventsForDate as _getEventsForDate, formatSubmittedAt } from './modules/event-utils.js';
import { WEEKDAY_NAMES } from './modules/date-constants.js';
import {
    switchTab,
    registerTabHook,
    setTabBadge,
    setTabBadgeDot,
    openManualAndScroll,
    goToAddException,
    goToExceptionsList,
    goToOpeningHours,
    generatePeriodName,
} from './admin/tabs.js';
import { state } from './admin/state.js';
import { loadVacancies, openVacancyDialog, cancelVacancy, loadChangeLog } from './admin/vacancy.js';
import { openShareModal, closeShareModal, shareDownloadPng, shareDownloadPdf, shareCopyMessage } from './admin/share.js';
import { setDirty, setClean, initDirtyTrackers } from './admin/dirty-tracker.js';
import {
    loadSyncStatus,
    showSyncLogs,
    loadSyncSettings,
    saveSyncKeyword,
    showSetupWizard,
    hideSetupWizard,
    wizardConnect,
    wizardBack,
    wizardSave,
    wizardSkip,
    showSyncKeywordCard,
} from './admin/sync.js';
import {
    renderImportPreview,
    refreshPreviewIfVisible,
    goToCreatePeriod,
    initSyncDateRange,
    showSettingsDayPopup,
    closeSettingsDayPopup,
    saveSettingsPopup,
    deleteSettingsPopup,
    loadOpeningHours,
    saveOpeningHours,
    loadExceptions,
    addException,
    deleteException,
    exportOpeningHours,
    importOpeningHours,
} from './admin/opening-hours.js';
import {
    loadMembersTab,
    loadInviteCode,
    generateInviteCode,
    copyInviteUrl,
    toggleInviteCode,
    loadInvitations,
    createInvitation,
    revokeInvitation,
    loadMembers,
    changeMemberRole,
    removeMember,
    updateMemberAttributes,
} from './admin/members.js';
import {
    loadBuilderPeriodSelect,
    loadBuilderData,
    closeAdminDayPopup,
    toggleWorkerAssignment,
    applyWorkerTime,
    saveSchedule,
    submitForApproval,
    confirmSchedule,
} from './admin/builder.js';
import {
    loadPeriods,
    archivePeriod,
    unarchivePeriod,
    deletePeriod,
    gotoArchivedPeriods,
    promptArchiveAfterConfirm,
    createPeriod,
    updatePeriodStatus,
    editPeriodAnnouncement,
    closeAnnouncementEditor,
    saveAnnouncement,
    publishPeriod,
    sendPeriodReminder,
} from './admin/periods.js';
import {
    loadReminderSettings,
    saveReminderSettings,
    loadLevelSettings,
    renderLevelSettings,
    addLevelTier,
    removeLevelTier,
    moveLevelTier,
    saveLevelSettings,
    loadOverlapCheckSettings,
    saveOverlapCheckSettings,
    loadMinAttendanceSettings,
    renderMinAttendanceSettings,
    saveMinAttendanceSettings,
    loadStaffingRequirements,
    renderStaffingList,
    addStaffingRow,
    removeStaffingRow,
    updateStaffingField,
    saveStaffingRequirements,
    loadWorkflowSettings,
    updateWorkflowWarning,
    saveWorkflowSettings,
    inviteOwner,
    gotoOwnerInvite,
} from './admin/settings.js';



function setupStaticHandlers() {
    document.getElementById('btn-logout').addEventListener('click', () => {
        location.href = '/auth/logout';
    });

    // Tab buttons
    document.querySelectorAll('.tab-btn[data-tab]').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Sync buttons
    document.getElementById('btn-import-hours').addEventListener('click', () => importOpeningHours());
    document.getElementById('btn-export-hours').addEventListener('click', () => exportOpeningHours());

    // Preview action buttons
    document.getElementById('btn-go-create-period').addEventListener('click', () => goToCreatePeriod());
    document.getElementById('btn-go-add-exception').addEventListener('click', () => goToAddException());
    document.getElementById('btn-go-exceptions-list').addEventListener('click', () => goToExceptionsList());
    document.getElementById('btn-go-opening-hours').addEventListener('click', () => goToOpeningHours());

    // Manual settings
    document.getElementById('btn-save-opening-hours').addEventListener('click', () => saveOpeningHours());
    document.getElementById('btn-add-exception').addEventListener('click', () => addException());

    // Periods
    document.getElementById('btn-create-period').addEventListener('click', () => createPeriod());
    const includeArchivedToggle = document.getElementById('periods-include-archived');
    if (includeArchivedToggle) {
        includeArchivedToggle.addEventListener('change', (e) => {
            state.periodsIncludeArchived = e.target.checked;
            loadPeriods();
        });
    }
    const btnGotoArchived = document.getElementById('btn-goto-archived-periods');
    if (btnGotoArchived) {
        btnGotoArchived.addEventListener('click', () => gotoArchivedPeriods());
    }

    // Builder
    document.getElementById('builder-period-select').addEventListener('change', () => loadBuilderData());
    document.getElementById('btn-save-schedule').addEventListener('click', () => saveSchedule());
    document.getElementById('btn-submit-approval').addEventListener('click', () => submitForApproval());
    document.getElementById('confirm-btn').addEventListener('click', () => confirmSchedule());
    document.getElementById('btn-refresh-builder').addEventListener('click', () => loadBuilderData());

    // Members tab
    const btnGenerate = document.getElementById('btn-generate-invite-code');
    if (btnGenerate) btnGenerate.addEventListener('click', () => generateInviteCode());
    const btnRegenerate = document.getElementById('btn-regenerate-invite-code');
    if (btnRegenerate) btnRegenerate.addEventListener('click', () => generateInviteCode());
    const btnCopy = document.getElementById('btn-copy-invite-url');
    if (btnCopy) btnCopy.addEventListener('click', () => copyInviteUrl());
    const enableToggle = document.getElementById('invite-code-enabled-toggle');
    if (enableToggle) enableToggle.addEventListener('change', (e) => toggleInviteCode(e.target.checked));
    const btnCreateInvitation = document.getElementById('btn-create-invitation');
    if (btnCreateInvitation) btnCreateInvitation.addEventListener('click', () => createInvitation());

    // Reminder settings
    const btnSaveReminder = document.getElementById('btn-save-reminder-settings');
    if (btnSaveReminder) btnSaveReminder.addEventListener('click', () => saveReminderSettings());

    // Level settings
    const levelEnabled = document.getElementById('level-system-enabled');
    if (levelEnabled) levelEnabled.addEventListener('change', (e) => {
        state.levelSystemState.enabled = e.target.checked;
        renderLevelSettings();
    });
    const btnAddLevelTier = document.getElementById('btn-add-level-tier');
    if (btnAddLevelTier) btnAddLevelTier.addEventListener('click', () => addLevelTier());
    const btnSaveLevel = document.getElementById('btn-save-level-settings');
    if (btnSaveLevel) btnSaveLevel.addEventListener('click', () => saveLevelSettings());

    // Overlap check settings
    const btnSaveOverlap = document.getElementById('btn-save-overlap-check');
    if (btnSaveOverlap) btnSaveOverlap.addEventListener('click', () => saveOverlapCheckSettings());

    // Min attendance settings
    const minMode = document.getElementById('min-attendance-mode');
    if (minMode) minMode.addEventListener('change', (e) => {
        state.minAttendanceState.mode = e.target.value;
        renderMinAttendanceSettings();
    });
    const minUnit = document.getElementById('min-attendance-unit');
    if (minUnit) minUnit.addEventListener('change', (e) => {
        state.minAttendanceState.unit = e.target.value;
        renderMinAttendanceSettings();
    });
    const btnSaveMinAtt = document.getElementById('btn-save-min-attendance');
    if (btnSaveMinAtt) btnSaveMinAtt.addEventListener('click', () => saveMinAttendanceSettings());

    // Workflow (approval process) settings
    const workflowToggle = document.getElementById('workflow-approval-required');
    if (workflowToggle) workflowToggle.addEventListener('change', () => updateWorkflowWarning());
    const btnSaveWorkflow = document.getElementById('btn-save-workflow');
    if (btnSaveWorkflow) btnSaveWorkflow.addEventListener('click', () => saveWorkflowSettings());
    const btnGotoOwnerInvite = document.getElementById('btn-goto-owner-invite');
    if (btnGotoOwnerInvite) btnGotoOwnerInvite.addEventListener('click', () => gotoOwnerInvite());
    const btnInviteOwner = document.getElementById('btn-invite-owner');
    if (btnInviteOwner) btnInviteOwner.addEventListener('click', () => inviteOwner());

    // Sync keyword settings
    const btnSaveSyncKeyword = document.getElementById('btn-save-sync-keyword');
    if (btnSaveSyncKeyword) btnSaveSyncKeyword.addEventListener('click', () => saveSyncKeyword());

    // Setup wizard
    const btnWizardConnect = document.getElementById('btn-wizard-connect');
    if (btnWizardConnect) btnWizardConnect.addEventListener('click', () => wizardConnect());
    const btnWizardSkip = document.getElementById('btn-wizard-skip');
    if (btnWizardSkip) btnWizardSkip.addEventListener('click', () => wizardSkip());
    const btnWizardSave = document.getElementById('btn-wizard-save');
    if (btnWizardSave) btnWizardSave.addEventListener('click', () => wizardSave());
    const btnWizardBack = document.getElementById('btn-wizard-back');
    if (btnWizardBack) btnWizardBack.addEventListener('click', () => wizardBack());
}

function setupDelegatedHandlers() {
    // Click delegation for dynamically generated elements
    document.addEventListener('click', (e) => {
        const target = e.target.closest('[data-action]');
        if (!target) return;
        const action = target.dataset.action;
        switch (action) {
            case 'showSyncLogs': showSyncLogs(); break;
            case 'showSettingsDayPopup': showSettingsDayPopup(target.dataset.date); break;
            case 'closeSettingsDayPopup': closeSettingsDayPopup(); break;
            case 'saveSettingsPopup': saveSettingsPopup(target.dataset.date, target.dataset.excId === 'null' ? null : Number(target.dataset.excId)); break;
            case 'deleteSettingsPopup': deleteSettingsPopup(Number(target.dataset.excId)); break;
            case 'deleteException': deleteException(Number(target.dataset.id)); break;
            case 'updatePeriodStatus': updatePeriodStatus(Number(target.dataset.id), target.dataset.status); break;
            case 'archivePeriod': archivePeriod(Number(target.dataset.id), target.dataset.name); break;
            case 'unarchivePeriod': unarchivePeriod(Number(target.dataset.id)); break;
            case 'deletePeriod': deletePeriod(Number(target.dataset.id), target.dataset.name); break;
            case 'closeAdminDayPopup': closeAdminDayPopup(); break;
            case 'toggleWorkerAssignment': toggleWorkerAssignment(Number(target.dataset.userId), target.dataset.date); break;
            case 'revokeInvitation': revokeInvitation(Number(target.dataset.id)); break;
            case 'removeMember': removeMember(Number(target.dataset.id), target.dataset.name); break;
            case 'removeLevelTier': removeLevelTier(target.dataset.key, target.dataset.label, Number(target.dataset.count)); break;
            case 'moveLevelTierUp': moveLevelTier(target.dataset.key, -1); break;
            case 'moveLevelTierDown': moveLevelTier(target.dataset.key, 1); break;
            case 'openVacancyDialog': openVacancyDialog(Number(target.dataset.entryId)); break;
            case 'cancelVacancy': cancelVacancy(Number(target.dataset.id)); break;
            case 'sendPeriodReminder': sendPeriodReminder(Number(target.dataset.periodId)); break;
            case 'openShareModal': openShareModal(Number(target.dataset.periodId)); break;
            case 'closeShareModal': closeShareModal(); break;
            case 'shareDownloadPng': shareDownloadPng(); break;
            case 'shareDownloadPdf': shareDownloadPdf(); break;
            case 'shareCopyMessage': shareCopyMessage(); break;
            case 'editPeriodAnnouncement': editPeriodAnnouncement(Number(target.dataset.periodId)); break;
            case 'saveAnnouncement': saveAnnouncement(); break;
            case 'closeAnnouncementEditor': closeAnnouncementEditor(); break;
            case 'publishPeriod': publishPeriod(Number(target.dataset.periodId)); break;
            case 'addStaffingRow': addStaffingRow(); break;
            case 'removeStaffingRow': removeStaffingRow(Number(target.dataset.index)); break;
            case 'saveStaffingRequirements': saveStaffingRequirements(); break;
        }
    });

    // Change delegation for dynamically generated time inputs
    document.addEventListener('change', (e) => {
        const target = e.target.closest('[data-action]');
        if (!target) return;
        if (target.dataset.action === 'applyWorkerTime') {
            applyWorkerTime(Number(target.dataset.userId), target.dataset.date);
        }
        if (target.dataset.action === 'updateStaffingField') {
            updateStaffingField(
                Number(target.dataset.index),
                target.dataset.field,
                target.value,
            );
        }
        if (target.dataset.action === 'changeMemberRole') {
            changeMemberRole(Number(target.dataset.memberId), target.value);
        }
        if (target.dataset.action === 'changeMemberLevel') {
            const memberId = Number(target.dataset.memberId);
            const value = target.value || null;
            updateMemberAttributes(memberId, { level_key: value })
                .then(() => {
                    showToast('レベルを更新しました', 'success');
                    // Refresh tier member counts on settings tab
                    loadLevelSettings();
                })
                .catch(() => loadMembers());
        }
        if (target.dataset.action === 'changeMemberMinCount' || target.dataset.action === 'changeMemberMinHours') {
            const memberId = Number(target.dataset.memberId);
            const raw = target.value;
            const parsed = raw === '' ? null : Number(raw);
            const key = target.dataset.action === 'changeMemberMinCount'
                ? 'min_attendance_count_per_week' : 'min_attendance_hours_per_week';
            updateMemberAttributes(memberId, { [key]: parsed })
                .then(() => showToast('最低出勤設定を更新しました', 'success'))
                .catch(() => loadMembers());
        }
    });
}



async function init() {
    setupStaticHandlers();
    setupDelegatedHandlers();
    initDirtyTrackers();
    // タブ切替時の副作用（旧 switchTab 内のタブ別分岐）をフックとして登録
    registerTabHook('builder', () => {
        loadBuilderPeriodSelect();
        loadChangeLog();
        loadVacancies();
    });
    registerTabHook('members', () => loadMembersTab());
    // periods.js が archive/unarchive/delete 時に発火する変更通知。builder 側の
    // 期間ドロップダウンを再取得する（builder.js 抽出後はそちらで listen 予定）。
    document.addEventListener('admin:periods-changed', () => {
        loadBuilderPeriodSelect();
    });
    try {
        state.currentUser = await getCurrentUser();
        document.getElementById('user-name').textContent = state.currentUser.display_name || state.currentUser.email;
        initSyncDateRange();
        const results = await Promise.allSettled([
            loadSyncStatus(),
            loadOpeningHours(),
            loadExceptions(),
            loadPeriods(),
            loadReminderSettings(),
            loadSyncSettings(),
            loadLevelSettings(),
            loadOverlapCheckSettings(),
            loadMinAttendanceSettings(),
            loadStaffingRequirements(),
            loadWorkflowSettings(),
            loadInvitations(),
        ]);
        const statusData = results[0].status === 'fulfilled' ? results[0].value : null;
        const syncSettings = results[5].status === 'fulfilled' ? results[5].value : null;

        // Show setup wizard or keyword card
        const isConfigured = syncSettings && syncSettings.calendar_setup_dismissed;
        const hasCalExceptions = statusData && statusData.calendar_exceptions && statusData.calendar_exceptions.count > 0;
        const needsSetup = !isConfigured && !hasCalExceptions;
        if (needsSetup) {
            showSetupWizard();
        } else {
            showSyncKeywordCard();
        }
        setTabBadgeDot('settings', needsSetup);

        // Show preview calendar based on calendar exceptions range
        if (statusData && statusData.calendar_exceptions && statusData.calendar_exceptions.count > 0) {
            renderImportPreview(
                statusData.calendar_exceptions.min_date,
                statusData.calendar_exceptions.max_date
            );
        }

        // 初期表示タブの決定: セットアップ未完了なら設定タブ、通常運用ならシフト構築タブ
        switchTab(needsSetup ? 'settings' : 'builder');
    } catch (e) {
        console.error('Init error:', e);
    }
}






init().finally(() => { if (window.lucide) lucide.createIcons(); });
